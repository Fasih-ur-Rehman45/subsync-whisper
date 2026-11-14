import gizmo
from subsync import subtitle
from subsync.synchro import pipeline, dictionary, encdetect, wordsdump, controller
from subsync.synchro import transcribe, translate, route
from subsync.data import languages
import os
from subsync.translations import _
from subsync.error import Error
import threading
import time

import logging
logger = logging.getLogger(__name__)


# transcription of audio (for languages without speech recognition model) stops
# as soon as synchronization found by matching words is confirmed by speech of
# the whole file (see transcribe.refineFormula), but not before this many
# chunks were transcribed (the first and the last one)
transcriptMinChunks = 2
# when speech confirms a formula but transcribed chunks or regions of the movie
# disagree with it this many times, subtitles do not fit the movie as a whole
# (e.g. made for a different cut) and synchronization fails without
# transcribing the rest; correctly matching subtitles were seen with 1 at most
transcriptMaxMismatches = 3


class Synchronizer(object):
    def __init__(self, sub, ref):
        self.sub = sub
        self.ref = ref

        self.onUpdate = lambda: None
        self.onError = lambda src, err: None
        self.onInitProgress = lambda msg: None

        self.stats = gizmo.CorrelationStats()
        self.effortBegin = None
        self.statsLock = threading.Lock()
        # formula polished with speech activity, overrides correlator's one
        self.refinedFormula = None
        # offset of every subtitle line, when synchronized piecewise
        self.piecewiseOffsets = None

        # matching method for this language pair, see route.py
        self.route = None
        # subtitles machine-translated to English for matching (route.PIVOT):
        # pipeline of their words, and English text by line start (ms)
        self.subWordsPipeline = None
        self.matchTexts = None

        self.correlator = None
        self.translator = None
        self.subPipeline = None
        self.refPipelines = []
        self.pipelines = []
        self.wordsDumpers = []

    def destroy(self):
        logger.info('releasing synchronizer resources')

        if self.correlator:
            self.correlator.stop(force=True)

        for p in self.pipelines:
            p.stop()

        for p in self.pipelines:
            p.destroy()

        if self.correlator:
            self.correlator.wait()
            self.correlator.connectStatsCallback(None)

        self.subPipeline = None
        self.subWordsPipeline = None
        self.refPipelines = []
        self.pipelines = []
        self.translator = None
        self.dictionary = None
        self.refWordsSink = None

        for wd in self.wordsDumpers:
            wd.flush()

        self.wordsDumpers = []

    def init(self, options, runCb=None):
        try:
            self._initInternal(options, runCb)
        except (gizmo.ErrorTerminated, transcribe.Terminated, translate.Terminated):
            logger.info('initialization terminated')

    def _leadTarget(self):
        ''' How long before speech lines should start: subtitles of
        English-language films do it later than of other films (see
        transcribe.leadTarget). '''
        english = self.ref.lang and self.ref.lang.lower() == 'eng'
        return transcribe.leadTargetEnglish if english else transcribe.leadTarget

    def _subRunning(self):
        return any(p and p.isRunning() for p in (self.subPipeline, self.subWordsPipeline))

    def _translateSubtitles(self, runCb=None):
        ''' Machine-translate subtitles to English for matching (route.PIVOT).
        Returns path of the English subtitles (same timing), or `None` when the
        subtitles can't be read here (e.g. a stream inside a video file). '''
        import pysubs2
        try:
            subs = pysubs2.load(self.sub.path, encoding=self.sub.enc or 'utf-8')
        except Exception as err:
            logger.warning('subtitles cannot be read for translation: %r', err)
            return None

        events = sorted((e for e in subs.events if not e.is_comment), key=lambda e: e.start)
        texts = [ e.plaintext for e in events ]
        src = route.code2(self.sub.lang)

        def progress(done, total):
            self.onInitProgress(_('Translating subtitles for matching: {} of {} lines')
                    .format(done, total))

        if translate.isModelInstalled() is False:
            # normally downloaded before synchronization starts, after asking
            self.onInitProgress(_('Downloading translation model (first use only)...'))
            if not translate.downloadModel(runCb=runCb):
                raise translate.Terminated()

        logger.info('translating %i subtitle lines from %s to English for matching',
                len(texts), src)
        english = translate.getTranslation(texts, src, runCb=runCb, progressCb=progress)

        self.matchTexts = {}
        for event, text in zip(events, english):
            self.matchTexts.setdefault(event.start, []).append(text)

        path = os.path.splitext(translate.getCachePath(texts, src))[0] + '.srt'
        transcribe.writeSrt(path, [ (e.start / 1000.0, e.end / 1000.0, text or '...')
            for e, text in zip(events, english) ])
        return path

    def _matchText(self, start, text):
        ''' Text a subtitle line (starting at `start` ms) is matched with. '''
        if self.matchTexts is None:
            return text
        return ' '.join(self.matchTexts.get(start) or [ text ])

    def _createTranscriptPipeline(self, options, runCb=None):
        ''' There is no pocketsphinx model for some languages (e.g. Japanese),
        audio in such language is transcribed by whisper, chunk by chunk, and
        transcript is used as a reference instead of the audio stream.
        '''
        if not transcribe.isAvailable():
            raise Error(_('Synchronization with {} audio requires faster-whisper '
                'package, install it with: pip install faster-whisper')
                .format(self.ref.lang)).add('language', self.ref.lang)

        # speech is translated to English by whisper for English subtitles and
        # for subtitles matched through English (see route.py), it works better
        # than matching words through the dictionary
        toEnglish = route.translatesSpeech(self.route, self.ref)
        lang = route.transcriptLanguage(self.route, self.ref)
        logger.info('transcribing %s audio from "%s" (route: %s, translate: %s)',
                self.ref.lang, self.ref.path, self.route, toEnglish)

        pipe = pipeline.TranscriptPipeline(self.ref, lang, toEnglish, runCb=runCb)
        pipe.statusCb = lambda msg: self.onInitProgress(msg)

        # transcription is slow, it stops as soon as the result is confirmed;
        # when user asked to try as hard as possible, whole file is transcribed
        # and only then the result is polished
        self.thorough = options.get('minEffort', 1.0) >= 1.0
        self.minWordLen = options.get('minWordLen', 5)
        # transcript lines are compared with subtitles in the transcript
        # language, in letter groups for languages written without spaces
        self.ngrams = languages.get(lang).ngrams
        self.transcriptMismatches = 0
        pipe.isDoneCb = lambda chunks: self._isTranscriptEnough(pipe, chunks)

        return pipe, lang

    def _isTranscriptEnough(self, pipe, chunksDone):
        ''' Called after every transcribed chunk. Synchronization found by
        matching words so far is polished with speech detected in the whole
        file (see transcribe.refineFormula). When speech confirms it, polished
        formula is used and transcription stops, otherwise next chunk is needed.
        '''
        if chunksDone < transcriptMinChunks:
            return False
        if self.thorough and chunksDone < pipe.chunksNo:
            return False

        # wait until all words pushed so far are correlated
        deadline = time.monotonic() + 60.0
        while pipe._isRunning() and self.correlator.isRunning() \
                and time.monotonic() < deadline \
                and (self._subRunning() or self.correlator.getProgress() < 1.0):
            time.sleep(0.05)

        with self.statsLock:
            stats = self.stats
        if not stats.correlated:
            logger.info('after %i transcript chunks: not correlated yet', chunksDone)
            return False

        speech = transcribe.loadSpeech(pipe.cacheDir)
        if not speech:
            logger.warning('no speech detected, synchronization cannot be confirmed')
            return False

        with self.subtitlesCollector.subtitlesLock:
            subs = [ (e.start / 1000.0, e.end / 1000.0, self._matchText(e.start, e.text))
                    for e in self.subtitlesCollector.getSubtitles().events ]

        res = transcribe.refineFormula([ s[:2] for s in subs ], speech,
                stats.formula.a, stats.formula.b)
        if res is None:
            logger.info('after %i transcript chunks: %s not confirmed by speech',
                    chunksDone, stats.formula)
            return False

        # speech overlap judges the whole file at once, every transcribed chunk
        # must agree on its own too (subtitles could be made for another cut)
        chunks = [ transcribe.readSrt(transcribe.getChunkPath(pipe.cacheDir, no))
                for no in pipe.chunksDoneList ]
        if not transcribe.checkChunks(subs, chunks, res[0], res[1], self.minWordLen,
                self.ngrams):
            logger.info('after %i transcript chunks: %.6fx%+.3f not confirmed by '
                    'transcribed chunks', chunksDone, res[0], res[1])
            return self._transcriptMismatch(subs, speech, chunks, res)

        # and every region of the movie must fit speech, transcribed or not
        if not transcribe.checkRegions([ s[:2] for s in subs ], speech, res[0], res[1]):
            logger.info('after %i transcript chunks: %.6fx%+.3f not confirmed by '
                    'speech in every region', chunksDone, res[0], res[1])
            return self._transcriptMismatch(subs, speech, chunks, res)

        # lines start a moment before speech, like correct subtitles do
        shift = transcribe.leadShift([ (res[0] * s[0] + res[1], res[0] * s[1] + res[1])
            for s in subs ], speech, self._leadTarget())
        with self.statsLock:
            self.refinedFormula = gizmo.Line(res[0], res[1] + shift)
        logger.info('after %i transcript chunks: %s confirmed by speech, polished to %s',
                chunksDone, stats.formula, self.refinedFormula)
        return 'confirmed'

    def _transcriptMismatch(self, subs, speech, chunks, formula):
        ''' Speech fits a formula on the whole, but part of the movie does not.
        After `transcriptMaxMismatches` such results, subtitles are likely made
        for a different cut of the movie: they are synchronized piecewise
        (see transcribe.alignPiecewise), and when the pieces are confirmed by
        transcribed chunks and by speech in every region, that is the result.
        Otherwise transcription stops and synchronization fails. '''
        self.transcriptMismatches += 1
        if self.transcriptMismatches < transcriptMaxMismatches:
            return False

        logger.info('subtitles do not fit one formula (%i mismatches), '
                'trying piecewise synchronization', self.transcriptMismatches)
        a = formula[0]
        offsets = transcribe.alignPiecewise([ s[:2] for s in subs ], speech, a, formula[1])
        pieces = len(set(round(o, 3) for o in offsets or []))

        if offsets and pieces > 1:
            mapped = [ (a * s[0] + o, a * s[1] + o, s[2]) for s, o in zip(subs, offsets) ]
            if transcribe.checkChunks(mapped, chunks, 1.0, 0.0, self.minWordLen, self.ngrams) \
                    and transcribe.checkRegions([ m[:2] for m in mapped ], speech, 1.0, 0.0):
                # lines start a moment before speech, like correct subtitles do
                shift = transcribe.leadShift([ m[:2] for m in mapped ], speech, self._leadTarget())
                offsets = [ o + shift for o in offsets ]
                # formula of the longest piece is the one shown
                main = max(set(offsets), key=offsets.count)
                with self.statsLock:
                    self.piecewiseOffsets = offsets
                    self.refinedFormula = gizmo.Line(a, main)
                logger.info('piecewise synchronization confirmed, %i pieces', pieces)
                return 'confirmed'
            logger.info('piecewise synchronization not confirmed')

        logger.warning('subtitles do not fit the movie (%i mismatches), stopping',
                self.transcriptMismatches)
        return 'mismatch'

    def _initInternal(self, options, runCb=None):
        logger.info('initializing synchronization jobs')
        for stream in (self.sub, self.ref):
            if stream.type == 'subtitle/text' and not stream.enc and len(stream.streams) == 1:
                stream.enc = encdetect.detectEncoding(stream.path, stream.lang)

        self.correlator = gizmo.Correlator(
                options['windowSize'],
                options['minCorrelation'],
                options['maxPointDist'],
                options['minPointsNo'],
                options['minWordsSim'])
        self.correlator.connectStatsCallback(self.onStatsUpdate)
        self.refWordsSink = self.correlator.pushRefWord
        self.subtitlesCollector = subtitle.SubtitlesCollector()

        self.route = route.getRoute(self.sub, self.ref)
        englishPath = None
        if self.route == route.PIVOT:
            englishPath = self._translateSubtitles(runCb)
            if englishPath is None:
                self.route = route.DICTIONARY if transcribe.supports(self.ref.lang) else route.ORIGINAL
        logger.info('matching route: %s', self.route)

        # subtitles are read from the original file (they are what is saved);
        # when translated for matching, words come from the English copy
        self.subPipeline = pipeline.createProducerPipeline(self.sub)
        self.subPipeline.connectEosCallback(self.onSubEos)
        self.subPipeline.connectErrorCallback(self.onSubError)
        self.subPipeline.addSubsListener(self.subtitlesCollector.addSubtitle)
        self.subPipeline.addSubsListener(self.correlator.pushSubtitle)
        if englishPath:
            from subsync.synchro.input import SubFile
            self.subWordsPipeline = pipeline.SubtitlePipeline(
                    SubFile(path=englishPath, lang='eng', enc='UTF-8'), runCb)
            self.subWordsPipeline.connectEosCallback(self.onSubEos)
            self.subWordsPipeline.connectErrorCallback(self.onSubError)
            self.subWordsPipeline.addWordsListener(self.correlator.pushSubWord)
        else:
            self.subPipeline.addWordsListener(self.correlator.pushSubWord)

        refLang = self.ref.lang
        subLang = route.matchLanguage(self.route, self.sub)
        transcriptPipe = None
        if self.ref.type == 'audio' and self.route in route.WHISPER:
            transcriptPipe, refLang = self._createTranscriptPipeline(options, runCb)

        if subLang and refLang and subLang != refLang:
            self.dictionary = dictionary.loadDictionary(refLang, subLang, options['minWordLen'])
            self.translator = gizmo.Translator(self.dictionary)
            self.translator.setMinWordsSim(options['minWordsSim'])
            self.translator.addWordsListener(self.correlator.pushRefWord)
            self.refWordsSink = self.translator.pushWord

        if transcriptPipe:
            self.refPipelines = [ transcriptPipe ]
        else:
            self.refPipelines = pipeline.createProducerPipelines(self.ref, no=options['jobsNo'], runCb=runCb)

        for p in self.refPipelines:
            p.connectEosCallback(self.onRefEos)
            p.connectErrorCallback(self.onRefError)
            p.addWordsListener(self.refWordsSink)

        subPipelines = [ p for p in (self.subPipeline, self.subWordsPipeline) if p ]
        self.pipelines = subPipelines + self.refPipelines

        for p in self.pipelines:
            p.configure(
                    minWordLen=options['minWordLen'],
                    minWordProb=options['minWordProb'])

        dumpSources = {
                'sub':     [ self.subPipeline ],
                'subPipe': [ self.subPipeline ],
                'subRaw':  [ (self.subWordsPipeline or self.subPipeline).getRawWordsSource() ],
                'ref':     [ self.translator ] if self.translator else self.refPipelines,
                'refPipe': self.refPipelines,
                'refRaw':  [ p.getRawWordsSource() for p in self.refPipelines ],
                }

        for srcId, path in options.get('dumpWords', []):
            sources = dumpSources.get(srcId)
            if sources:
                logger.debug('dumping %s to %s (from %i sources)', srcId, path, len(sources))
                if path:
                    wd = wordsdump.WordsFileDump(path, overwrite=True)
                else:
                    wd = wordsdump.WordsStdoutDump(srcId)
                self.wordsDumpers.append(wd)
                for source in sources:
                    source.addWordsListener(wd.pushWord)

    def start(self):
        logger.info('starting synchronization')
        self.correlator.start('Correlator')
        for id, p in enumerate(self.pipelines):
            p.start('Pipeline{}'.format(id))

    def stop(self, force=True):
        logger.info('stopping synchronizer')
        self.correlator.stop(force=force)

        for p in self.pipelines:
            p.stop()

    def isRunning(self):
        if self.correlator and self.correlator.isRunning():
            return True

        for p in self.pipelines:
            if p.isRunning():
                return True

        return False

    def getProgress(self):
        psum = 0.0
        plen = 0

        for pr in  [ p.getProgress() for p in self.pipelines ]:
            if pr != None:
                psum += pr
                plen += 1

        if self.correlator:
            cp = self.correlator.getProgress()
            res = cp * cp
        else:
            res = 0.0

        if plen > 0:
            res *= psum / plen

        if res < 0: res = 0
        if res > 1: res = 1
        return res

    def getStatus(self):
        with self.statsLock:
            stats = self.stats
            refined = self.refinedFormula
            progress = self.getProgress()
            begin = self.effortBegin
        formula = refined or stats.formula

        effort = -1
        # with transcribed audio, transcript pipeline decides itself how much
        # audio is needed (see _isTranscriptEnough); progress based effort
        # would stop synchronization too early, especially when transcript
        # chunks come from the cache all at once and still wait in the
        # correlator queue after transcription ends
        transcript = any(isinstance(p, pipeline.TranscriptPipeline) for p in self.refPipelines)
        # with transcribed audio, only formula confirmed by speech and by every
        # transcribed chunk is trusted; otherwise synchronization fails rather
        # than saving subtitles that may be badly wrong
        correlated = refined is not None if transcript else stats.correlated
        if begin is not None and begin < 1.0 and not transcript:
            if progress <= 0.0:
                effort = 0.0
            elif progress >= 1.0:
                effort = 1.0
            else:
                effort = (progress - begin) / (1.0 - begin)

        return controller.SyncStatus(
                correlated  = correlated and self.subPipeline and not self._subRunning(),
                maxChange   = self.subtitlesCollector.getMaxSubtitleDiff(formula),
                progress    = progress,
                factor      = stats.factor,
                points      = stats.points,
                formula     = formula,
                effort      = effort)

    def getSynchronizedSubtitles(self):
        with self.statsLock:
            formula = self.refinedFormula or self.stats.formula
            offsets = self.piecewiseOffsets
        if offsets:
            return self.subtitlesCollector.getSynchronizedSubtitlesPiecewise(
                    formula.a, offsets)
        return self.subtitlesCollector.getSynchronizedSubtitles(formula)

    def onStatsUpdate(self, stats):
        logger.debug(stats)
        with self.statsLock:
            self.stats = stats
            if self.effortBegin == None and stats.correlated and self.subPipeline and not self._subRunning():
                self.effortBegin = self.getProgress()
        self.onUpdate()

    def onSubEos(self):
        logger.info('subtitles read done')
        self.checkIfAllPipelinesDone()
        with self.statsLock:
            if self.effortBegin == None and self.stats.correlated:
                self.effortBegin = self.getProgress()

    def onRefEos(self):
        logger.info('references read done')
        self.checkIfAllPipelinesDone()

    def checkIfAllPipelinesDone(self):
        for p in self.pipelines:
            if p.isRunning():
                return
        logger.info('stopping correlator')
        self.correlator.stop(force=False)
        self.onUpdate()

    def onSubError(self, err):
        logger.warning('SUB: %r', str(err).replace('\n', '; '))
        self.onError('sub', err)

    def onRefError(self, err):
        logger.warning('REF: %r', str(err).replace('\n', '; '))
        self.onError('ref', err)
