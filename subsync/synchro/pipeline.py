import gizmo
from subsync.synchro import speech, transcribe
from subsync.data import languages
from subsync.translations import _
from subsync.error import Error
import math
import threading
import time

import logging
logger = logging.getLogger(__name__)


class BasePipeline(object):
    def __init__(self, stream, runCb=None):
        self.demux = gizmo.Demux(stream.path, runCb)
        self.extractor = gizmo.Extractor(self.demux)

        self.duration = max(self.demux.getDuration(), 0)
        self.timeWindow = [0, self.duration]

    def destroy(self):
        self.extractor.stop()
        self.extractor.wait()
        self.extractor.connectEosCallback(None)
        self.extractor.connectErrorCallback(None)

    def selectTimeWindow(self, begin, end=math.inf):
        if begin != 0.0:
            self.demux.seek(begin)
        if end is not math.inf:
            self.extractor.selectEndTime(end)
        else:
            end = self.duration
        self.timeWindow = (begin, end)

    def start(self, threadName=None):
        self.extractor.start(threadName=threadName)

    def stop(self):
        self.extractor.stop()

    def isRunning(self):
        return self.extractor.isRunning()

    def getProgress(self):
        if self.duration:
            pos = self.demux.getPosition()
            if math.isclose(pos, 0.0):
                pos = self.timeWindow[0]
            if self.timeWindow[1] > self.timeWindow[0]:
                return (pos - self.timeWindow[0]) / (self.timeWindow[1] - self.timeWindow[0])

    def getPosition(self):
        return max(self.timeWindow[0], min(self.demux.getPosition(), self.timeWindow[1]))

    def connectErrorCallback(self, cb):
        self.extractor.connectErrorCallback(cb)

    def connectEosCallback(self, cb):
        self.extractor.connectEosCallback(cb)


class SubtitlePipeline(BasePipeline):
    def __init__(self, stream, runCb=None):
        ''' Speech recognition pipeline:

        Demux --> SpeechDec --[words]--> {NgramSplitter} --[words]--> ...
        '''

        super().__init__(stream, runCb)
        self.dec = gizmo.SubtitleDec()
        self.ngramSplitter = None
        self.sink = self.dec

        langInfo = stream.lang and languages.get(code3=stream.lang.lower())
        if langInfo:
            if langInfo.rightToLeft:
                logger.info('switching to right-to-left for file "%s"', stream.path)
                self.dec.setRightToLeft(True)

            if langInfo.ngrams:
                logger.info('switching to %i-gram for file "%s"', langInfo.ngrams, stream.path)
                self.dec.setMinWordLen(langInfo.ngrams)
                self.ngramSplitter = gizmo.NgramSplitter(langInfo.ngrams)
                self.dec.addWordsListener(self.ngramSplitter.pushWord)
                self.sink = self.ngramSplitter

        if stream.enc != None:
            self.dec.setEncoding(stream.enc)

        self.demux.connectDec(self.dec, stream.no)

    def configure(self, minWordLen, minWordProb=None):
        if self.ngramSplitter is None:
            self.dec.setMinWordLen(minWordLen)

    def destroy(self):
        super().destroy()
        self.dec.removeWordsListener()
        self.dec.removeSubsListener()
        self.sink.removeWordsListener()

    def addWordsListener(self, listener):
        self.sink.addWordsListener(listener)

    def removeWordsListener(self, listener=None):
        return self.sink.removeWordsListener(listener)

    def getRawWordsSource(self):
        return self.dec

    def addSubsListener(self, listener):
        self.dec.addSubsListener(listener)

    def removeSubsListener(self, listener=None):
        self.dec.removeSubsListener(listener)


class SpeechPipeline(BasePipeline):
    def __init__(self, stream, runCb=None):
        ''' Speech recognition pipeline:

        Demux --> AudioDec --> Resampler --> SpeechRecognition --[words]--> {NgramSplitter} --[words]--> ...
        '''

        super().__init__(stream, runCb)

        speechModel = speech.loadSpeechModel(stream.lang)
        self.dec = gizmo.AudioDec()

        speechAudioFormat = speech.getSpeechAudioFormat(speechModel)
        logger.info('speech recognition audio format: %s', speechAudioFormat)

        self.speechRec = speech.createSpeechRec(speechModel)
        self.ngramSplitter = None
        self.sink = self.speechRec

        langInfo = stream.lang and languages.get(code3=stream.lang.lower())
        if langInfo and langInfo.ngrams:
            logger.info('switching to %i-gram for audio "%s"', langInfo.ngrams, stream.path)
            self.speechRec.setMinWordLen(langInfo.ngrams)
            self.ngramSplitter = gizmo.NgramSplitter(langInfo.ngrams)
            self.speechRec.addWordsListener(self.ngramSplitter.pushWord)
            self.sink = self.ngramSplitter

        self.resampler = gizmo.Resampler()
        self.channels = stream.channels
        self.resampler.connectFormatChangeCallback(self.onAudioFormatChanged)

        self.demux.connectDec(self.dec, stream.no)
        self.dec.connectOutput(self.resampler)
        self.resampler.connectOutput(self.speechRec, speechAudioFormat)

    def configure(self, minWordLen, minWordProb):
        self.speechRec.setMinWordProb(minWordProb)
        if self.ngramSplitter is None:
            self.speechRec.setMinWordLen(minWordLen)

    def destroy(self):
        super().destroy()
        self.sink.removeWordsListener()
        self.speechRec.removeWordsListener()
        self.resampler.connectFormatChangeCallback(None)

    def onAudioFormatChanged(self, inFormat, outFormat):
        logger.info('input audio format: %s', inFormat)
        channelsMap = self.channels.getLayoutMap(inFormat.channelLayout)
        logger.info('listening to channels: %s', channelsMap)
        self.resampler.setChannelMap(channelsMap.getMap())

    def addWordsListener(self, listener):
        self.sink.addWordsListener(listener)

    def removeWordsListener(self, listener=None):
        return self.sink.removeWordsListener(listener)

    def getRawWordsSource(self):
        return self.speechRec


class TranscriptPipeline(object):
    def __init__(self, stream, lang, translate=False, runCb=None):
        ''' Speech transcription pipeline, for languages without speech
        recognition model (see transcribe.py):

        whisper --[SRT chunks]--> SubtitlePipeline --[words]--> ...

        Audio is transcribed in chunks spread over the whole file, every chunk
        is read as subtitles as soon as it is ready. Transcription stops early
        when `isDoneCb` (called with number of chunks done) returns True.

        lang is language of the transcript (3-letter code), English when
        `translate` is set.
        '''
        self.stream = stream
        self.lang = lang
        self.translate = translate
        self.runCb = runCb
        self.isDoneCb = None
        self.statusCb = None    # called with status message for the user

        self.listeners = []
        self.minWordLen = None
        self.eosCb = None
        self.errorCb = None

        self.thread = None
        self.running = False
        self.stopping = False
        self.finished = False
        # where transcript chunks and detected speech are kept
        self.cacheDir = transcribe.getCacheDir(stream.path, stream.no, stream.lang, translate)
        self.duration = 0.0
        self.position = 0.0
        self.chunksNo = 0
        self.chunksDone = 0
        self.chunksDoneList = []    # numbers of transcribed chunks, in order

    def configure(self, minWordLen, minWordProb=None):
        self.minWordLen = minWordLen

    def destroy(self):
        self.stop()
        if self.thread:
            self.thread.join()
        self.listeners = []
        self.eosCb = None
        self.errorCb = None

    def start(self, threadName=None):
        self.running = True
        self.thread = threading.Thread(target=self._run,
                name=threadName or 'Transcript', daemon=True)
        self.thread.start()

    def stop(self):
        self.stopping = True

    def isRunning(self):
        return self.running

    def getProgress(self):
        if self.finished:
            return 1.0
        if self.duration:
            return min(self.position / self.duration, 1.0)
        return 0.0

    def connectErrorCallback(self, cb):
        self.errorCb = cb

    def connectEosCallback(self, cb):
        self.eosCb = cb

    def addWordsListener(self, listener):
        self.listeners.append(listener)

    def removeWordsListener(self, listener=None):
        if listener is None:
            self.listeners = []
        elif listener in self.listeners:
            self.listeners.remove(listener)

    def getRawWordsSource(self):
        return self

    def _isRunning(self):
        return not self.stopping and (self.runCb is None or self.runCb())

    def _status(self, msg):
        if self.statusCb:
            self.statusCb(msg)

    def _run(self):
        self._status(_('Transcribing audio, preparing...'))
        self.lastStatusMinute = None
        try:
            self.finished = transcribe.getTranscriptChunks(
                    self.stream.path, self.stream.no, self.stream.lang,
                    translate=self.translate,
                    runCb=self._isRunning,
                    progressCb=self._onProgress,
                    chunkCb=self._onChunk,
                    planCb=self._onPlan)

        except transcribe.Terminated:
            logger.info('transcription terminated')

        except Exception as err:
            logger.warning('transcription failed: %r', err, exc_info=True)
            if self.errorCb:
                self.errorCb(Error(_('Audio transcription failed, {}').format(err))
                        .add('path', self.stream.path)
                        .add('language', self.stream.lang))

        finally:
            self.running = False
            if self.eosCb:
                self.eosCb()

    def _onPlan(self, chunks):
        self.chunksNo = len(chunks)
        if chunks:
            self.duration = chunks[-1][1]

    def _onProgress(self, position, duration):
        self.position = position
        if duration:
            self.duration = duration

        minute = int(position // 60)
        if minute != self.lastStatusMinute and self.duration:
            self.lastStatusMinute = minute
            self._status(_('Transcribing audio: {} of {} min').format(
                minute, int(round(self.duration / 60))))

    def _onChunk(self, no, path):
        ''' Feed transcribed chunk as subtitles, returns True to stop
        transcription. '''
        if not self._isRunning():
            return True

        lines = transcribe.readSrt(path)
        logger.info('transcript chunk %i ready, %i lines', no + 1, len(lines))

        # ffmpeg fails on empty subtitle files, there may be no speech in chunk
        if lines:
            from subsync.synchro.input import RefFile
            pipe = SubtitlePipeline(RefFile(path=path, lang=self.lang, enc='UTF-8'),
                    self.runCb)
            try:
                if self.minWordLen is not None:
                    pipe.configure(minWordLen=self.minWordLen)
                for listener in self.listeners:
                    pipe.addWordsListener(listener)
                pipe.connectErrorCallback(lambda err: logger.warning(
                    'TRANSCRIPT: %r', str(err).replace('\n', '; ')))
                pipe.start('TranscriptChunk')
                while pipe.isRunning():
                    time.sleep(0.02)
            finally:
                pipe.destroy()

        self.chunksDone += 1
        self.chunksDoneList.append(no)
        res = self.isDoneCb(self.chunksDone) if self.isDoneCb else False

        if res == 'mismatch':
            logger.info('subtitles do not fit after %i/%i chunks, '
                    'transcription stopped', self.chunksDone, self.chunksNo)
            self._status(_('Subtitles do not fit this video, stopping...'))
            if self.errorCb:
                self.errorCb(Error(_('Subtitles do not fit this video as a whole, '
                    'they may be made for a different cut or release'))
                    .add('path', self.stream.path))
            self.finished = True
            return True

        if res:
            logger.info('synchronization confirmed after %i/%i chunks, '
                    'transcription stopped', self.chunksDone, self.chunksNo)
            self._status(_('Timing confirmed, finishing...'))
            self.finished = True
            return True
        return False


def createProducerPipeline(stream, runCb=None):
    if stream.type == 'subtitle/text':
        return SubtitlePipeline(stream, runCb)
    elif stream.type == 'audio':
        return SpeechPipeline(stream, runCb)
    else:
        raise Error(_('Not supported stream type'), type=stream.type)


def createProducerPipelines(stream, no=None, runCb=None):
    pipes = []
    for i in range(no):
        p = createProducerPipeline(stream, runCb)
        pipes.append(p)

        if p.duration:
            if p.duration / (i+1) < 5*60:
                logger.info('using only %i jobs due to short duration', i+1)
                break
        else:
            logger.info('cannot get duration - using single pipeline')
            break

    if len(pipes) > 1:
        no = len(pipes)
        duration = pipes[0].duration
        partTime = duration / no
        for i, p in enumerate(pipes):
            begin = i * partTime
            end = begin + partTime + 1.0 # overlap to catch whole words
            if end >= duration:
                end = math.inf
            logger.info('job %i/%i time window set to %.2f - %.2f', i+1, no, begin, end)

            try:
                p.selectTimeWindow(begin, end)
            except gizmo.Error:
                logger.warning('seek failed, using only %i jobs', i, exc_info=True)
                no = i
                pipes = pipes[:no]
                if pipes:
                    logger.info('updating job %i/%i time window set to %.2f - %.2f',
                            no, no, begin - partTime, duration)
                    pipes[-1].selectTimeWindow(begin - partTime, duration)
                break

    return pipes
