"""Whisper based transcription, for languages without a pocketsphinx model.

SubSync recognises speech with pocketsphinx, which has no model for Japanese
and many other languages. For such languages the audio is transcribed here
(with the optional faster-whisper package) to timed text lines, which are then
used as a subtitle reference.

Audio is split to chunks of a few minutes, cut in quiet moments, and every
chunk is transcribed to its own SRT file. During synchronization chunks are
transcribed in an order spread over the whole file (first, last, middle...),
so synchronization could stop as soon as its result is stable, without
transcribing the whole movie. Chunks are cached in the temporary directory, so
synchronizing against the same file again does not repeat the transcription.

This module deliberately imports nothing from subsync or gizmo, so it can also
be run on its own to produce a reference for an unmodified SubSync:

    python subsync/synchro/transcribe.py video.mkv

Environment variables:
    SUBSYNC_WHISPER_MODEL    model size or path (default: small)
    SUBSYNC_WHISPER_DEVICE   cpu, cuda or auto (default: cpu)
    SUBSYNC_WHISPER_COMPUTE  ctranslate2 compute type (default: int8)
    SUBSYNC_WHISPER_PYTHON   Python with faster-whisper, when SubSync's own
                             Python does not have it (default: .whisper next
                             to the sources)
"""

import hashlib
import json
import os
import sys
import tempfile

import logging
logger = logging.getLogger(__name__)


# 3-letter language code => whisper language code, for languages that have no
# pocketsphinx speech model
languages = {
        'alb': 'sq', 'ara': 'ar', 'bel': 'be', 'bul': 'bg', 'cat': 'ca',
        'cze': 'cs', 'dan': 'da', 'est': 'et', 'fao': 'fo', 'fin': 'fi',
        'glg': 'gl', 'heb': 'he', 'hrv': 'hr', 'hun': 'hu', 'ice': 'is',
        'ind': 'id', 'jpn': 'ja', 'kor': 'ko', 'lat': 'la', 'lav': 'lv',
        'lit': 'lt', 'may': 'ms', 'mlg': 'mg', 'mlt': 'mt', 'nor': 'no',
        'per': 'fa', 'pol': 'pl', 'por': 'pt', 'rum': 'ro', 'slo': 'sk',
        'slv': 'sl', 'srp': 'sr', 'swe': 'sv', 'tur': 'tr', 'ukr': 'uk',
        }

sampleRate = 16000

# audio is transcribed in chunks of about this length (seconds), so memory use
# does not grow with the length of the movie and synchronization could stop
# before the whole movie is transcribed
chunkLength = 300.0
# chunks are cut in the quietest moment of this long window (seconds) around
# their nominal border, to not split a sentence in the middle
chunkCutWindow = 60.0
# resolution of the audio energy used to find quiet moments (seconds)
energyStep = 0.25

# whisper times a line from the first to the last spoken word, while subtitle
# lines usually appear at speech start and stay on screen longer, to be read;
# SubSync spreads words evenly over the line display time, so the transcript is
# timed like subtitles are, otherwise synchronized subtitles would come early;
# measured on two movies, subtitles start ~0.3 s after whisper lines and end
# ~0.7-1.1 s after them, with these values synchronization error was < 0.02 s
lineLeadIn = 0.3
lineLeadOut = 1.0
lineReadingSpeed = 17.0     # characters per second
lineMinDuration = 0.833
lineMaxDuration = 7.0
lineMinGap = 0.083

# bump when transcript content or timing changes, to not reuse old cache
cacheVersion = 3

# speech is detected (for refineFormula) in blocks of this length (seconds);
# pauses shorter than speechMinSilence (seconds) do not split it
speechBlockLength = 300.0
speechMinSilence = 0.3

# synchronization found by matching words of a few transcript chunks is
# polished with speech of the whole file (see refineFormula), searched this
# close to it: speed (as a fraction) and offset (seconds)
refineScaleRange = 4e-4
refineOffsetRange = 3.0
# polished result must be the best one in this much wider offset range too
refineWideRange = 60.0
refineStep = 0.01   # seconds

# every transcribed chunk must agree with the synchronization formula on its
# own (see checkChunks), otherwise subtitles may not fit one formula at all,
# e.g. they were made for a different cut of the movie: words of transcript
# lines are matched with subtitle lines up to checkWindow seconds away, and
# the time differences of matches must cluster around zero (+-checkTolerance)
checkWindow = 120.0
checkTolerance = 2.0
checkMinLines = 10      # chunks with fewer transcript lines are not judged
checkMinMatches = 3
checkMinChunks = 2      # this many chunks must agree

# speech of the whole file is checked region by region too (see checkRegions),
# as transcribed chunks may miss the part of the movie that does not fit:
# subtitles of every region are moved up to regionSearch seconds against
# detected speech, the best fit must be within regionTolerance seconds
regionLength = 900.0
regionMinLines = 30     # regions with fewer subtitle lines are not judged
regionSearch = 60.0
regionTolerance = 1.0
regionMargin = 1.2      # fit elsewhere must be this much better to disagree

# subtitles made for a different cut of the movie (scenes added or removed)
# are synchronized piecewise (see alignPiecewise): offsets of regions are
# searched this far (seconds) around the formula; changing the offset between
# subtitle lines costs piecewiseSplitCost (seconds of speech overlap, roughly
# 20 subtitle lines worth), so only clear evidence splits the subtitles
piecewiseRange = 600.0
piecewiseSplitCost = 10.0
piecewiseFineRange = 0.5    # each piece is then fine tuned this far


class Terminated(Exception):
    """Transcription was cancelled by the caller."""


class NotInstalled(Exception):
    """faster-whisper package is not installed."""

    def __init__(self):
        super().__init__('faster-whisper is not installed, '
                'install it with: pip install faster-whisper')


def supports(lang):
    """Check whether audio in this language (3-letter code) is handled here."""
    return bool(lang) and lang.lower() in languages


def isAvailable():
    """Check whether faster-whisper is installed, here or in separate Python."""
    return _hasModule() or bool(findPython())


def translates(refLang, subLang):
    """Check whether speech should be translated to English, instead of being
    transcribed. It is much more reliable for English subtitles than matching
    the transcript through the dictionary."""
    return supports(refLang) and bool(subLang) and subLang.lower() == 'eng'


def defaultModel():
    return os.environ.get('SUBSYNC_WHISPER_MODEL') or 'small'


def formatTime(seconds):
    ms = max(int(round(seconds * 1000.0)), 0)
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return '{:02d}:{:02d}:{:02d},{:03d}'.format(h, m, s, ms)


def parseTime(text):
    hms, _, ms = text.strip().partition(',')
    h, m, s = hms.split(':')
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms or 0) / 1000.0


# --- audio decoding --------------------------------------------------------

def _openAudio(container, path, streamNo):
    stream = None
    if streamNo is not None and 0 <= streamNo < len(container.streams):
        stream = container.streams[streamNo]
        if stream.type != 'audio':
            stream = None
    if stream is None:
        if not container.streams.audio:
            raise ValueError('there is no audio stream in {}'.format(path))
        stream = container.streams.audio[0]
    return stream


def _frames(container, stream, runCb):
    """Decoded audio frames, followed by `None` (to flush the resampler)."""
    for no, frame in enumerate(container.decode(stream)):
        if runCb and no % 256 == 0 and not runCb():
            raise Terminated()
        yield frame
    yield None


class _SpeechDetector(object):
    """Detects speech, with voice activity detector of faster-whisper, in
    audio pushed in pieces. Appends (start, end) times to `result`."""

    def __init__(self, result):
        try:
            from faster_whisper.vad import VadOptions, get_speech_timestamps
        except ImportError:
            raise NotInstalled()
        self.detect = get_speech_timestamps
        self.options = VadOptions(
                min_silence_duration_ms=int(speechMinSilence * 1000),
                speech_pad_ms=0)
        self.result = result
        self.pending, self.size, self.offset = [], 0, 0

    def push(self, data):
        self.pending.append(data)
        self.size += len(data)
        if self.size >= speechBlockLength * sampleRate:
            self.flush()

    def flush(self):
        import numpy as np
        if self.size:
            audio = np.concatenate(self.pending).astype(np.float32) / 32768.0
            for item in self.detect(audio, self.options):
                self.result.append((
                    round((self.offset + item['start']) / sampleRate, 3),
                    round((self.offset + item['end']) / sampleRate, 3)))
            self.offset += len(audio)
            self.pending, self.size = [], 0


def planChunks(path, streamNo=None, runCb=None, length=None, speech=None):
    """Split audio stream to chunks of about `length` seconds, cut in the
    quietest moments.

    When `speech` list is given, it is filled with (start, end) times of speech
    detected in the whole stream.

    Returns
    -------
    list of (float, float)
        Chunks start and end times, in seconds.
    """
    import av
    import numpy as np

    length = length or chunkLength
    step = int(sampleRate * energyStep)
    energy, rest, total = [], np.zeros(0, dtype=np.float32), 0
    detector = _SpeechDetector(speech) if speech is not None else None

    with av.open(path) as container:
        stream = _openAudio(container, path, streamNo)
        resampler = av.AudioResampler(format='s16', layout='mono', rate=sampleRate)
        for frame in _frames(container, stream, runCb):
            for out in resampler.resample(frame):
                data = out.to_ndarray().reshape(-1)
                if detector:
                    detector.push(data)
                data = data.astype(np.float32)
                total += len(data)
                if len(rest):
                    data = np.concatenate((rest, data))
                count = len(data) // step
                if count:
                    energy.append(np.square(data[:count * step]).reshape(count, step).mean(axis=1))
                rest = data[count * step:]

    if detector:
        detector.flush()

    duration = total / sampleRate
    if duration <= 0:
        return []

    energy = np.concatenate(energy) if energy else np.zeros(0)
    pairs = energy[:-1] + energy[1:]    # 0.5 s windows
    count = max(int(round(duration / length)), 1)
    half = chunkCutWindow / 2.0 / energyStep

    cuts = [ 0.0 ]
    for no in range(1, count):
        center = no * duration / count / energyStep
        lo, hi = int(max(center - half, 0)), int(min(center + half, len(pairs)))
        if hi > lo:
            # cut in the middle of the quietest window
            cut = (lo + int(np.argmin(pairs[lo:hi])) + 1) * energyStep
            if cuts[-1] < cut < duration:
                cuts.append(cut)
    cuts.append(duration)
    return list(zip(cuts[:-1], cuts[1:]))


def decodeRange(path, streamNo=None, start=0.0, end=None, runCb=None):
    """Decode audio between `start` and `end` seconds to mono 16 kHz float32
    numpy array. streamNo is 0-based stream index in the container, `None` for
    the first audio stream."""
    import av
    import numpy as np

    first = int(round(start * sampleRate))
    size = None if end is None else int(round(end * sampleRate)) - first

    def decode(seek):
        chunks, got, pos = [], 0, None
        with av.open(path) as container:
            stream = _openAudio(container, path, streamNo)
            if seek:
                # lands on the last packet before `start`
                container.seek(int(start / stream.time_base), stream=stream)
            resampler = av.AudioResampler(format='s16', layout='mono', rate=sampleRate)

            for frame in _frames(container, stream, runCb):
                if pos is None and frame is not None:
                    if not seek:
                        pos = 0
                    elif frame.time is None:
                        return None     # position unknown, decode from start
                    else:
                        pos = int(round(frame.time * sampleRate))
                        if pos > first:     # seek landed too far, keep timing
                            chunks.append(np.zeros(pos - first, dtype=np.int16))
                            got = pos - first

                for out in resampler.resample(frame):
                    data = out.to_ndarray().reshape(-1)
                    if pos < first:
                        skip = min(first - pos, len(data))
                        data, pos = data[skip:], pos + skip
                    if len(data):
                        chunks.append(data)
                        got += len(data)
                        pos += len(data)

                if size is not None and got >= size:
                    break

        audio = np.concatenate(chunks) if chunks else np.zeros(0, dtype=np.int16)
        return audio if size is None else audio[:size]

    audio = decode(seek=start > 0)
    if audio is None:
        audio = decode(seek=False)
    return audio.astype(np.float32) / 32768.0


# --- transcription ---------------------------------------------------------

def timeLines(lines):
    """Time transcript lines like subtitles, see `lineLeadIn` and following.

    lines is list of (start, end, text) tuples, sorted by start time.
    """
    res = []
    for no, (start, end, text) in enumerate(lines):
        begin = start + lineLeadIn
        finish = max(end + lineLeadOut, begin + len(text) / lineReadingSpeed,
                begin + lineMinDuration)
        finish = min(finish, begin + lineMaxDuration)
        if no + 1 < len(lines):
            finish = min(finish, lines[no + 1][0] + lineLeadIn - lineMinGap)
        # never shorter than the speech itself
        res.append((begin, max(finish, end), text))
    return res


def loadModel(model=None):
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        raise NotInstalled()

    model = model or defaultModel()
    device = os.environ.get('SUBSYNC_WHISPER_DEVICE') or 'cpu'
    compute = os.environ.get('SUBSYNC_WHISPER_COMPUTE') or 'int8'
    logger.info('loading whisper model %s (%s, %s)', model, device, compute)
    return WhisperModel(model, device=device, compute_type=compute)


def transcribeRange(whisper, path, streamNo, start, end, lang, translate=False,
        runCb=None, progressCb=None):
    """Transcribe audio between `start` and `end` seconds.

    Returns
    -------
    list of (float, float, str)
        Lines start time, end time and text, timed like subtitles.
    """
    audio = decodeRange(path, streamNo, start, end, runCb)

    # voice detection and no conditioning on previous text keeps whisper from
    # inventing lines during music or silence, which would spoil the timing;
    # greedy decoding (beam_size=1) is about twice as fast as the default beam
    # search, worse wording does not matter for synchronization
    segments, _info = whisper.transcribe(audio,
            language=lang,
            task='translate' if translate else 'transcribe',
            beam_size=1,
            vad_filter=True,
            condition_on_previous_text=False,
            word_timestamps=True)

    lines = []
    for segment in segments:
        if runCb and not runCb():
            raise Terminated()

        text = ' '.join(segment.text.split())
        if text and segment.end > segment.start:
            lines.append((start + segment.start, start + segment.end, text))

        if progressCb:
            progressCb(start + segment.end)

    return timeLines(lines)


def spreadOrder(count):
    """Chunk indices ordered to cover the whole file as soon as possible:
    first, last, middle, quarters and so on."""
    if count <= 0:
        return []
    order = [ 0 ]
    if count > 1:
        order.append(count - 1)
    left = set(range(count)) - set(order)
    while left:
        best = max(sorted(left), key=lambda no: min(abs(no - x) for x in order))
        order.append(best)
        left.remove(best)
    return order


def getChunkPath(outDir, no):
    return os.path.join(outDir, 'chunk-{:03d}.srt'.format(no))


def loadPlan(outDir):
    try:
        with open(os.path.join(outDir, 'plan.json'), encoding='utf-8') as fp:
            return [ tuple(x) for x in json.load(fp)['chunks'] ]
    except (OSError, ValueError, KeyError, TypeError):
        return None


def loadSpeech(outDir):
    """Speech (start, end) times detected in the whole audio stream, `None`
    when not detected yet."""
    try:
        with open(os.path.join(outDir, 'plan.json'), encoding='utf-8') as fp:
            return [ tuple(x) for x in json.load(fp)['speech'] ]
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _savePlan(outDir, chunks, speech=None):
    path = os.path.join(outDir, 'plan.json')
    data = { 'chunks': chunks }
    if speech is not None:
        data['speech'] = speech
    with open(path + '.part', 'w', encoding='utf-8') as fp:
        json.dump(data, fp)
    os.replace(path + '.part', path)


def refineFormula(subs, speech, a, b):
    """Polish synchronization formula with speech of the whole file.

    Formula (synchronized time = a * subtitle time + b) found by matching words
    of a few transcript chunks is right within a second or so. Here speed and
    offset are searched close to it, for the best overlap of subtitle lines with
    detected speech. That uses the whole file and needs no language knowledge,
    but alone it could settle on a wrong answer far away; starting from matched
    words and checking a much wider range prevents that.

    Parameters
    ----------
    subs: list of (float, float)
        Subtitle lines start and end times (not synchronized), sorted.
    speech: list of (float, float)
        Speech start and end times, see `loadSpeech`.

    Returns
    -------
    tuple of (float, float) or None
        Polished a and b, or `None` when speech does not confirm the formula:
        best overlap is elsewhere, or at the edge of the searched range.
    """
    import numpy as np

    if not subs or not speech:
        return None

    step = refineStep
    near = int(round(refineOffsetRange / step))
    wide = int(round(refineWideRange / step))

    length = int(max(speech[-1][1], a * subs[-1][1] + b) / step) + 1
    size = 1 << (length + 2 * wide).bit_length()

    voice = np.zeros(size, dtype=np.float32)
    for start, end in speech:
        voice[int(round(start / step)):int(round(end / step))] = 1.0
    # subtitle shown over silence costs as much as shown over speech gains
    voice[:length] -= voice[:length].mean()
    voiceFft = np.fft.rfft(voice)

    def overlaps(scale):
        ''' Overlap of speech with subtitles moved by -wide .. +wide steps. '''
        shown = np.zeros(size, dtype=np.float32)
        for start, end in subs:
            i = int(round((scale * start + b) / step))
            j = int(round((scale * end + b) / step))
            if j > 0 and i < length:
                shown[max(i, 0):min(j, length)] = 1.0
        res = np.fft.irfft(voiceFft * np.conj(np.fft.rfft(shown)), size)
        return np.concatenate((res[-wide:], res[:wide + 1]))

    def best(scale):
        res = overlaps(scale)
        pos = wide - near + int(np.argmax(res[wide - near:wide + near + 1]))
        return float(res[pos]), scale, pos - wide, float(res.max())

    # coarse to fine search of the speed
    top = None
    width = refineScaleRange
    for count in (10, 4, 4):
        center = top[1] if top else a
        for no in range(-count, count + 1):
            res = best(center + no * width / count)
            if top is None or res[0] > top[0]:
                top = res
        width /= count

    score, scale, shift, widest = top
    logger.info('speech overlap: best for %.6fx%+.3f, words gave %.6fx%+.3f',
            scale, b + shift * step, a, b)

    if score <= 0.0:
        logger.info('subtitles do not overlap speech, not confirmed')
        return None
    if widest > score * 1.0001:
        logger.info('speech overlap is better far from this formula, not confirmed')
        return None
    if abs(shift) >= near or abs(scale - a) >= refineScaleRange * 0.999:
        logger.info('speech overlap is best at the edge of searched range, not confirmed')
        return None
    return scale, b + shift * step


def _words(text, minLen):
    import re
    text = re.sub(r'\{[^}]*\}|\\[Nnh]|<[^>]*>', ' ', text.lower())
    return set(w for w in re.findall(r'[^\W\d_]+', text) if len(w) >= minLen)


def checkChunks(subs, chunks, a, b, minWordLen=5):
    """Check that every transcribed chunk agrees with synchronization formula.

    Speech overlap (see `refineFormula`) looks at the whole file at once, so
    subtitles that fit one formula only in part of the movie (e.g. made for a
    different cut) could still pass it. Here words of transcript lines are
    matched with nearby subtitle lines, separately in every chunk. When the
    formula is right, time differences of the matches cluster around zero.

    Parameters
    ----------
    subs: list of (float, float, str)
        Subtitle lines start, end and text (not synchronized).
    chunks: list of list of (float, float, str)
        Transcript lines of every transcribed chunk.

    Returns
    -------
    bool
        `True` when no chunk disagrees and at least `checkMinChunks` agree.
    """
    import bisect

    subWords = sorted((a * start + b, _words(text, minWordLen)) for start, _, text in subs)
    subTimes = [ x[0] for x in subWords ]
    agree, disagree = 0, 0

    for no, lines in enumerate(chunks):
        if len(lines) < checkMinLines:
            continue

        diffs = []
        for start, _, text in lines:
            words = _words(text, minWordLen)
            if not words:
                continue
            lo = bisect.bisect_left(subTimes, start - checkWindow)
            hi = bisect.bisect_right(subTimes, start + checkWindow)
            # subtitle line sharing the most words; skipped when ambiguous
            # (words repeated in many lines, e.g. names, would match anywhere)
            best, found = 0, []
            for time, sw in subWords[lo:hi]:
                shared = len(words & sw)
                if shared > best:
                    best, found = shared, [ start - time ]
                elif shared and shared == best:
                    found.append(start - time)
            if found and max(found) - min(found) <= 2 * checkTolerance:
                diffs.append(sum(found) / len(found))

        near = sum(1 for d in diffs if abs(d) <= checkTolerance)
        # biggest cluster of differences elsewhere
        others = sorted(d for d in diffs if abs(d) > checkTolerance)
        other, j = 0, 0
        for i in range(len(others)):
            while others[i] - others[j] > 2 * checkTolerance:
                j += 1
            other = max(other, i - j + 1)

        # chunk with too few matches has no opinion, it disagrees only when
        # its matches clearly point elsewhere
        if near >= checkMinMatches and near > other:
            verdict = 'agrees'
            agree += 1
        elif other >= checkMinMatches and other >= near:
            verdict = 'DISAGREES'
            disagree += 1
        else:
            verdict = 'too few matches'
        logger.info('chunk check: %i lines, %i matches agree, %i in another cluster: %s',
                len(lines), near, other, verdict)

    return disagree == 0 and agree >= checkMinChunks


def checkRegions(subs, speech, a, b):
    """Check that subtitles fit detected speech with the formula in every
    region of the movie, not only on the whole.

    Transcribed chunks cover only a part of the movie, they could all fall on
    one side of a place where subtitles stop fitting the formula (e.g. made for
    a different cut). Speech is detected in the whole file, so here subtitles
    of every region of about `regionLength` seconds are moved against speech,
    and the best fit must be where the formula puts them.

    Parameters
    ----------
    subs: list of (float, float)
        Subtitle lines start and end times (not synchronized).
    speech: list of (float, float)
        Speech start and end times, see `loadSpeech`.

    Returns
    -------
    bool
        `True` when no region clearly fits speech elsewhere.
    """
    import numpy as np

    if not subs or not speech:
        return False

    step = refineStep
    search = int(round(regionSearch / step))
    tol = int(round(regionTolerance / step))

    lines = sorted((a * start + b, a * end + b) for start, end in subs)
    first, last = lines[0][0], lines[-1][0]
    count = max(int(round((last - first) / regionLength)), 1)
    width = (last - first) / count

    voiceAll = np.zeros(int(speech[-1][1] / step) + 1, dtype=np.float32)
    for start, end in speech:
        voiceAll[int(round(start / step)):int(round(end / step))] = 1.0
    mean = float(voiceAll.mean())

    disagree = 0
    for no in range(count):
        lo = first + no * width
        hi = lo + width if no + 1 < count else last + 1.0
        region = [ l for l in lines if lo <= l[0] < hi ]
        if len(region) < regionMinLines:
            logger.info('region check %s - %s: %i lines, not judged',
                    formatTime(lo)[:8], formatTime(hi)[:8], len(region))
            continue

        # speech around the region, with margin for moving subtitles
        origin = lo - regionSearch - 10.0
        length = int((hi - lo + 2 * regionSearch + 20.0) / step) + 1
        size = 1 << (length + 2 * search).bit_length()

        voice = np.zeros(size, dtype=np.float32)
        i0 = int(round(origin / step))
        src = voiceAll[max(i0, 0):max(i0 + length, 0)]
        if len(src):
            dst = max(-i0, 0)
            voice[dst:dst + len(src)] = src
        voice[:length] -= mean

        shown = np.zeros(size, dtype=np.float32)
        for start, end in region:
            shown[int(round((start - origin) / step)):int(round((end - origin) / step))] = 1.0

        res = np.fft.irfft(np.fft.rfft(voice) * np.conj(np.fft.rfft(shown)), size)
        res = np.concatenate((res[-search:], res[:search + 1]))
        pos = int(np.argmax(res))
        best, shift = float(res[pos]), (pos - search) * step
        here = float(res[search - tol:search + tol + 1].max())

        if abs(pos - search) <= tol:
            verdict = 'agrees'
        elif best > 0.0 and (here <= 0.0 or best > regionMargin * here):
            verdict = 'DISAGREES'
            disagree += 1
        else:
            verdict = 'unclear'
        logger.info('region check %s - %s: %i lines, best fit %+.2f s: %s',
                formatTime(lo)[:8], formatTime(hi)[:8], len(region), shift, verdict)

    return disagree == 0


def _regionOffsets(lines, speech, search):
    """Best offset (seconds) of every region's subtitle lines against speech,
    searched +-search seconds; lines are synchronized (start, end) times.
    Regions with fewer than `regionMinLines` lines are skipped."""
    import numpy as np

    step = refineStep
    width = int(round(search / step))
    voiceAll = np.zeros(int(speech[-1][1] / step) + 1, dtype=np.float32)
    for start, end in speech:
        voiceAll[int(round(start / step)):int(round(end / step))] = 1.0
    mean = float(voiceAll.mean())

    first, last = lines[0][0], lines[-1][0]
    count = max(int(round((last - first) / regionLength)), 1)
    span = (last - first) / count
    res = []
    for no in range(count):
        lo = first + no * span
        hi = lo + span if no + 1 < count else last + 1.0
        region = [ l for l in lines if lo <= l[0] < hi ]
        if len(region) < regionMinLines:
            continue
        origin = lo - search - 10.0
        length = int((hi - lo + 2 * search + 20.0) / step) + 1
        size = 1 << (length + 2 * width).bit_length()
        voice = np.zeros(size, dtype=np.float32)
        i0 = int(round(origin / step))
        src = voiceAll[max(i0, 0):max(i0 + length, 0)]
        if len(src):
            voice[max(-i0, 0):max(-i0, 0) + len(src)] = src
        voice[:length] -= mean
        shown = np.zeros(size, dtype=np.float32)
        for start, end in region:
            shown[int(round((start - origin) / step)):int(round((end - origin) / step))] = 1.0
        corr = np.fft.irfft(np.fft.rfft(voice) * np.conj(np.fft.rfft(shown)), size)
        corr = np.concatenate((corr[-width:], corr[:width + 1]))
        pos = int(np.argmax(corr))
        # best fit counts only when it is clearly better than any other one
        # (more than 2 regionTolerance away), searching far finds coincidences
        guard = int(round(2 * regionTolerance / step))
        rest = np.concatenate((corr[:max(pos - guard, 0)], corr[pos + guard + 1:]))
        second = float(rest.max()) if len(rest) else 0.0
        if corr[pos] > 0.0 and corr[pos] > regionMargin * max(second, 0.0):
            res.append((lo, hi, len(region), (pos - width) * step))
        else:
            logger.info('piecewise: region %s - %s, %i lines, no clear fit',
                    formatTime(lo)[:8], formatTime(hi)[:8], len(region))
    return res


def alignPiecewise(subs, speech, a, b):
    """Synchronize subtitles piecewise: lines get one of a few offsets.

    For subtitles made for a different cut of the movie, one formula cannot
    fit the whole movie. Speed (a) stays the same, but the offset changes
    where scenes were added or removed.

    First every region of the movie (see `checkRegions`) finds the offset
    where its subtitles fit detected speech best, searched up to
    `piecewiseRange` seconds; a region holds many lines, so that is reliable.
    These offsets (and the formula's own) are the only candidates. Then every
    subtitle line picks one of them by dynamic programming, maximizing overlap
    with speech, with a penalty for every change of the offset between
    consecutive lines. Finally every piece is fine tuned.

    Parameters
    ----------
    subs: list of (float, float)
        Subtitle lines start and end times (not synchronized), sorted.
    speech: list of (float, float)
        Speech start and end times, see `loadSpeech`.
    a, b: float
        Formula found so far.

    Returns
    -------
    list of float or None
        Offset of every line (synchronized time = a * time + offset), `None`
        when there is nothing to align.
    """
    import numpy as np

    if not subs or not speech:
        return None

    mapped = [ (a * start + b, a * end + b) for start, end in subs ]
    regions = _regionOffsets(mapped, speech, piecewiseRange)

    # candidate offsets: the formula's and those of the regions, merged when
    # closer than regionTolerance
    candidates = [ 0.0 ]
    for lo, hi, count, shift in regions:
        logger.info('piecewise: region %s - %s, %i lines, fits speech at %+.2f s',
                formatTime(lo)[:8], formatTime(hi)[:8], count, shift)
        if all(abs(shift - c) > regionTolerance for c in candidates):
            candidates.append(shift)

    fine = refineStep
    end = max(speech[-1][1], mapped[-1][1]) + piecewiseRange + 10.0
    voice = np.zeros(int(end / fine) + 1, dtype=np.float32)
    for start, stop in speech:
        voice[int(round(start / fine)):int(round(stop / fine))] = 1.0
    mean = float(voice[:int(speech[-1][1] / fine)].mean())
    cum = np.concatenate(([0.0], np.cumsum(voice, dtype=np.float64))) * fine
    lastIdx = len(cum) - 1

    def overlap(start, stop, shift):
        i0 = min(max(int(round((start + shift) / fine)), 0), lastIdx)
        i1 = min(max(int(round((stop + shift) / fine)), 0), lastIdx)
        return cum[i1] - cum[i0] - mean * (stop - start)

    # dynamic programming over lines and candidate offsets
    count = len(candidates)
    best = np.array([ overlap(mapped[0][0], mapped[0][1], c) for c in candidates ])
    choice = np.zeros((len(mapped), count), dtype=np.int64)
    choice[0] = np.arange(count)
    for no in range(1, len(mapped)):
        top = int(np.argmax(best))
        jump = best[top] - piecewiseSplitCost
        choice[no] = np.where(jump > best, top, np.arange(count))
        best = np.maximum(best, jump) + np.array(
                [ overlap(mapped[no][0], mapped[no][1], c) for c in candidates ])

    ks = np.zeros(len(mapped), dtype=np.int64)
    k = int(np.argmax(best))
    for no in range(len(mapped) - 1, -1, -1):
        ks[no] = k
        k = int(choice[no][k])

    # fine tune every piece (run of lines with the same offset)
    pieces, first = [], 0
    for no in range(1, len(mapped) + 1):
        if no == len(mapped) or ks[no] != ks[first]:
            pieces.append((first, no))
            first = no

    width = int(round(piecewiseFineRange / fine))
    fineSteps = np.arange(-width, width + 1)
    offsets = [ 0.0 ] * len(mapped)
    for first, last in pieces:
        shift = candidates[int(ks[first])]
        total = np.zeros(len(fineSteps))
        for start, stop in mapped[first:last]:
            i0 = np.clip(int(round((start + shift) / fine)) + fineSteps, 0, lastIdx)
            i1 = np.clip(int(round((stop + shift) / fine)) + fineSteps, 0, lastIdx)
            total += cum[i1] - cum[i0]
        shift += fineSteps[int(np.argmax(total))] * fine
        for no in range(first, last):
            offsets[no] = b + shift
        logger.info('piecewise: piece %s - %s, %i lines, offset %+.3f s',
                formatTime(mapped[first][0] + shift)[:8],
                formatTime(mapped[last - 1][0] + shift)[:8], last - first, b + shift)

    return offsets


def writeSrt(path, lines):
    tmpPath = path + '.part'
    try:
        with open(tmpPath, 'w', encoding='utf-8', newline='\n') as fp:
            for no, (start, end, text) in enumerate(lines, 1):
                fp.write('{}\n{} --> {}\n{}\n\n'.format(no,
                    formatTime(start), formatTime(end), text))
        os.replace(tmpPath, path)
    finally:
        if os.path.exists(tmpPath):
            os.remove(tmpPath)


def readSrt(path):
    lines = []
    with open(path, encoding='utf-8') as fp:
        for block in fp.read().split('\n\n'):
            rows = block.strip().split('\n')
            if len(rows) >= 3 and ' --> ' in rows[1]:
                start, end = rows[1].split(' --> ')
                lines.append((parseTime(start), parseTime(end), ' '.join(rows[2:])))
    return lines


def transcribeChunks(path, outDir, lang, streamNo=None, model=None,
        translate=False, order='spread', runCb=None, progressCb=None,
        chunkCb=None, planCb=None, detectSpeech=True):
    """Transcribe audio to SRT chunks `chunk-NNN.srt` in `outDir`.

    Chunks already present (e.g. from previous run) are not transcribed again.

    Parameters
    ----------
    lang: str
        Whisper language code, e.g. 'ja'.
    order: str, optional
        'spread' (see `spreadOrder`) or 'sequential'.
    runCb: callable, optional
        Polled during processing, transcription is cancelled (raising
        `Terminated`) when it returns `False`.
    progressCb: callable, optional
        Called with transcribed and total length, in seconds.
    chunkCb: callable, optional
        Called with chunk number and path when chunk is ready, transcription
        stops when it returns `True`.
    planCb: callable, optional
        Called with list of chunks (start, end) times before transcription.
    detectSpeech: bool, optional
        Detect speech in the whole stream too (see `loadSpeech`).

    Returns
    -------
    bool
        `True` if all chunks were transcribed, `False` if stopped by `chunkCb`.
    """
    os.makedirs(outDir, exist_ok=True)
    chunks = loadPlan(outDir)
    if chunks is None or (detectSpeech and loadSpeech(outDir) is None):
        logger.info('splitting audio to chunks%s', ', detecting speech' if detectSpeech else '')
        speech = [] if detectSpeech else None
        planned = planChunks(path, streamNo, runCb, speech=speech)
        if chunks is None:      # keep plan of chunks already transcribed
            chunks = planned
        _savePlan(outDir, chunks, speech)

    total = chunks[-1][1] if chunks else 0.0
    logger.info('audio split to %i chunks, %s total', len(chunks), formatTime(total))
    if planCb:
        planCb(chunks)

    indices = spreadOrder(len(chunks)) if order == 'spread' else range(len(chunks))
    whisper, done = None, 0.0

    for no in indices:
        start, end = chunks[no]
        chunkPath = getChunkPath(outDir, no)

        if not os.path.isfile(chunkPath):
            if whisper is None:
                whisper = loadModel(model)

            def chunkProgress(pos):
                if progressCb:
                    progressCb(done + min(max(pos - start, 0.0), end - start), total)

            logger.info('transcribing chunk %i/%i, %s - %s', no + 1, len(chunks),
                    formatTime(start), formatTime(end))
            lines = transcribeRange(whisper, path, streamNo, start, end, lang,
                    translate=translate, runCb=runCb, progressCb=chunkProgress)
            writeSrt(chunkPath, lines)

        done += end - start
        if progressCb:
            progressCb(done, total)
        if chunkCb and chunkCb(no, chunkPath):
            return False

    return True


def transcribe(path, outPath, lang, streamNo=None, model=None, runCb=None,
        progressCb=None, translate=False):
    """Transcribe audio from file `path` to single SRT file `outPath`.

    Returns
    -------
    int
        Number of subtitle lines written.
    """
    with tempfile.TemporaryDirectory(prefix='subsync-') as tmpDir:
        transcribeChunks(path, tmpDir, lang, streamNo=streamNo, model=model,
                translate=translate, order='sequential', runCb=runCb,
                progressCb=progressCb, detectSpeech=False)
        lines = []
        for no in range(len(loadPlan(tmpDir) or [])):
            lines += readSrt(getChunkPath(tmpDir, no))

    writeSrt(outPath, lines)
    logger.info('transcription done, %i lines written to %s', len(lines), outPath)
    return len(lines)


# --- running from SubSync --------------------------------------------------

def findPython():
    """Find Python interpreter with faster-whisper installed.

    SubSync itself may run under Python too old for faster-whisper, in such
    case transcription is run in a separate process, with interpreter set by
    SUBSYNC_WHISPER_PYTHON or installed in `.whisper` directory next to the
    sources.
    """
    path = os.environ.get('SUBSYNC_WHISPER_PYTHON')
    if path:
        return path if os.path.isfile(path) else None

    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    for sub in (('Scripts', 'python.exe'), ('bin', 'python')):
        path = os.path.join(root, '.whisper', *sub)
        if os.path.isfile(path):
            return path


def _hasModule():
    try:
        import faster_whisper
        return True
    except ImportError:
        return False


def _transcribeExternal(python, path, outDir, lang, streamNo=None, model=None,
        translate=False, runCb=None, progressCb=None, chunkCb=None, planCb=None):
    """Run `transcribeChunks` in a separate Python process."""
    import subprocess
    import threading

    cmd = [ python, os.path.abspath(__file__), path, '--chunks-dir', outDir,
            '-l', lang, '--machine' ]
    if model:
        cmd += [ '-m', model ]
    if streamNo is not None:
        cmd += [ '-s', str(streamNo + 1) ]
    if translate:
        cmd += [ '--translate' ]

    logger.info('running transcription: %s', ' '.join(cmd))
    flags = 0x08000000 if sys.platform == 'win32' else 0  # no console window
    env = dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONUTF8='1')
    proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE, creationflags=flags, env=env)

    state = { 'stop': False, 'error': None, 'complete': False }
    errors = []

    def reader():
        for raw in proc.stderr:
            line = raw.decode('utf-8', 'replace').strip()
            cmd, _, args = line.partition(' ')
            try:
                if state['stop']:
                    pass
                elif cmd == 'progress':
                    if progressCb:
                        progressCb(*map(float, args.split()))
                elif cmd == 'plan':
                    if planCb:
                        planCb(loadPlan(outDir) or [])
                elif cmd == 'chunk':
                    no = int(args)
                    if chunkCb and chunkCb(no, getChunkPath(outDir, no)):
                        state['stop'] = True
                elif cmd == 'done':
                    state['complete'] = True
                elif line:
                    errors.append(line)
                    del errors[:-20]
            except Exception as err:
                state['error'] = err
                state['stop'] = True

    thread = threading.Thread(target=reader, name='TranscribeReader', daemon=True)
    thread.start()

    try:
        while True:
            try:
                proc.wait(timeout=0.5)
                break
            except subprocess.TimeoutExpired:
                if state['stop']:
                    break
                if runCb and not runCb():
                    raise Terminated()
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
            # killed process had no chance to remove its partial output
            for name in os.listdir(outDir):
                if name.endswith('.part'):
                    os.remove(os.path.join(outDir, name))
        # chunks reported by the process may still be processed by chunkCb,
        # cached chunks are all reported at once, right before it exits
        while thread.is_alive():
            thread.join(timeout=0.5)
            if runCb and not runCb():
                state['stop'] = True

    if state['error']:
        raise state['error']
    if state['stop']:
        return False
    if proc.returncode != 0 or not state['complete']:
        raise RuntimeError('transcription process failed (code {}): {}'.format(
            proc.returncode, ' | '.join(errors[-5:])))
    return True


def getCacheDir(path, streamNo, lang, translate=False, model=None):
    """Directory where transcript chunks of this audio stream are cached."""
    lang2 = languages.get(lang.lower(), lang.lower())
    stat = os.stat(path)
    key = '|'.join(str(x) for x in (os.path.abspath(path), stat.st_size,
        stat.st_mtime_ns, streamNo, lang2, model or defaultModel(),
        'translate' if translate else '', chunkLength, cacheVersion))
    name = '{}.{}'.format(hashlib.sha1(key.encode('utf-8')).hexdigest()[:20],
            'en' if translate else lang2)
    return os.path.join(tempfile.gettempdir(), 'subsync-transcripts', name)


def getTranscriptChunks(path, streamNo, lang, translate=False, model=None,
        runCb=None, progressCb=None, chunkCb=None, planCb=None):
    """Transcribe audio stream to cached SRT chunks, in this process or in
    separate Python (see `findPython`). See `transcribeChunks` for callbacks.

    Parameters
    ----------
    lang: str
        3-letter language code (see `supports`) or whisper language code.
    translate: bool, optional
        Get English translation of the speech instead of the transcript.

    Returns
    -------
    bool
        `True` if all chunks were transcribed, `False` if stopped by `chunkCb`.
    """
    lang2 = languages.get(lang.lower(), lang.lower())
    model = model or defaultModel()
    outDir = getCacheDir(path, streamNo, lang, translate, model)
    os.makedirs(outDir, exist_ok=True)
    logger.info('transcript cache: %s', outDir)

    kw = dict(streamNo=streamNo, model=model, translate=translate, runCb=runCb,
            progressCb=progressCb, chunkCb=chunkCb, planCb=planCb)

    if _hasModule():
        return transcribeChunks(path, outDir, lang2, order='spread', **kw)

    python = findPython()
    if not python:
        raise NotInstalled()
    return _transcribeExternal(python, path, outDir, lang2, **kw)


def main(argv=None):
    import argparse

    parser = argparse.ArgumentParser(
            description='Transcribe audio to an SRT file usable as SubSync reference.')
    parser.add_argument('input', help='video or audio file')
    parser.add_argument('-o', '--output',
            help='output SRT path (default: <input name>.whisper.<lang>.srt)')
    parser.add_argument('-l', '--lang', default='ja',
            help='spoken language, whisper code (default: ja)')
    parser.add_argument('-s', '--stream', type=int,
            help='1-based stream number (default: first audio stream)')
    parser.add_argument('-m', '--model', help='whisper model size or path '
            '(default: {})'.format(defaultModel()))
    parser.add_argument('-t', '--translate', action='store_true',
            help='write English translation of the speech instead of the transcript')
    parser.add_argument('--overwrite', action='store_true',
            help='overwrite existing output file')
    parser.add_argument('--chunks-dir',
            help='write chunks to this directory, in spread order (used by SubSync)')
    parser.add_argument('--machine', action='store_true',
            help='print progress in machine readable form')
    args = parser.parse_args(argv)
    streamNo = None if args.stream is None else args.stream - 1

    def report(*items):
        sys.stderr.write(' '.join(str(x) for x in items) + '\n')
        sys.stderr.flush()

    def progress(pos, duration):
        if args.machine:
            report('progress', '{:.2f}'.format(pos), '{:.2f}'.format(duration))
        else:
            sys.stderr.write('\r{} / {}'.format(formatTime(pos), formatTime(duration)))
            sys.stderr.flush()

    try:
        if args.chunks_dir:
            transcribeChunks(args.input, args.chunks_dir, args.lang,
                    streamNo=streamNo, model=args.model, translate=args.translate,
                    progressCb=progress,
                    planCb=lambda chunks: report('plan', len(chunks)),
                    chunkCb=lambda no, path: report('chunk', no))
            report('done')
            return 0

        output = args.output
        if not output:
            outLang = 'en' if args.translate else args.lang
            output = '{}.whisper.{}.srt'.format(os.path.splitext(args.input)[0], outLang)

        if os.path.exists(output) and not args.overwrite:
            print('{} already exists, use --overwrite to replace it'.format(output),
                    file=sys.stderr)
            return 1

        count = transcribe(args.input, output, args.lang, streamNo=streamNo,
                model=args.model, progressCb=progress, translate=args.translate)

    except NotInstalled as err:
        print(err, file=sys.stderr)
        return 1

    sys.stderr.write('\n')
    print('{} lines written to {}'.format(count, output))
    return 0


if __name__ == '__main__':
    sys.exit(main())
