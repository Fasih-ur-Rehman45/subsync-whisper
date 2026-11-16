"""Unit tests for the alignment logic in subsync/synchro/transcribe.py.

They use synthetic films (see synthetic.py) with a known right answer, so they
run in seconds without videos, Whisper or the compiled engine:

    python -m unittest discover -s tests -v
"""

import logging
import random
import os
import tempfile
import unittest

from synthetic import transcribe as t, makeSpeech, makeSubtitles, mistime, cut, times, reword

logging.disable(logging.INFO)

# unusual speed and offset, not a standard frame rate ratio
SPEED, OFFSET = 1.0012, 7.3


def offsetErrors(fileLines, videoLines, a, offsets):
    """Error (seconds) of every synchronized line start."""
    return [ abs(a * f[0] + o - v[0]) for f, v, o in zip(fileLines, videoLines, offsets) ]


class TimeFormatTest(unittest.TestCase):
    def test_round_trip(self):
        for seconds in (0.0, 1.5, 59.999, 61.0, 3599.25, 7322.004):
            self.assertAlmostEqual(t.parseTime(t.formatTime(seconds)), seconds, places=3)

    def test_srt_round_trip(self):
        lines = [ (1.0, 2.5, 'first line'), (3600.125, 3601.0, 'second, with comma') ]
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'x.srt')
            t.writeSrt(path, lines)
            back = t.readSrt(path)
        self.assertEqual([ x[2] for x in back ], [ x[2] for x in lines ])
        for (s1, e1, _), (s2, e2, _) in zip(back, lines):
            self.assertAlmostEqual(s1, s2, places=3)
            self.assertAlmostEqual(e1, e2, places=3)


class TimeLinesTest(unittest.TestCase):
    """Transcript lines are retimed the way subtitles are shown."""

    lines = [ (10.0, 12.0, 'short'), (12.5, 13.0, 'x' * 100), (40.0, 41.0, 'a') ]

    def test_rules(self):
        res = t.timeLines(self.lines)
        for no, ((start, end, text), (begin, finish, _)) in enumerate(zip(self.lines, res)):
            self.assertAlmostEqual(begin, start + t.lineLeadIn)
            self.assertGreaterEqual(finish, end, 'never shorter than the speech')
            self.assertLessEqual(finish - begin, t.lineMaxDuration + 1e-9)
            if no + 1 < len(res):
                self.assertLessEqual(finish, res[no + 1][0] - t.lineMinGap + 1e-9,
                        'gap before the next line')

    def test_reading_time(self):
        begin, finish, _ = t.timeLines(self.lines)[1]
        self.assertGreaterEqual(finish - begin, min(100 / t.lineReadingSpeed, t.lineMaxDuration) - 1e-9)


class SpreadOrderTest(unittest.TestCase):
    def test_order(self):
        self.assertEqual(t.spreadOrder(0), [])
        self.assertEqual(t.spreadOrder(1), [ 0 ])
        for count in (2, 5, 24):
            order = t.spreadOrder(count)
            self.assertEqual(sorted(order), list(range(count)))
            self.assertEqual(order[:2], [ 0, count - 1 ])
        self.assertIn(t.spreadOrder(24)[2], (11, 12))


class FilmTest(unittest.TestCase):
    """Base: one synthetic film, its correct subtitles and a mistimed copy."""

    @classmethod
    def setUpClass(cls):
        cls.speech = makeSpeech(3600.0)
        cls.video = makeSubtitles(cls.speech)              # right in the video
        cls.file = mistime(cls.video, SPEED, OFFSET)       # as the file has them


class JapaneseTextTest(unittest.TestCase):
    """Japanese is written without spaces: whole phrases must not be treated
    as words, or differently worded transcript lines never match."""

    subtitle = '今夜はどこへ行くの、サツキ？'
    transcript = 'サツキ、今夜どこ行くの？'

    def test_phrases_alone_never_match(self):
        self.assertEqual(t._words(self.subtitle, 5) & t._words(self.transcript, 5), set())

    def test_letter_groups_match(self):
        shared = t._words(self.subtitle, 5, ngrams=3) & t._words(self.transcript, 5, ngrams=3)
        self.assertIn('サツキ', shared)
        self.assertIn('行くの', shared)

    def test_english_unchanged(self):
        self.assertEqual(t._words('Where are you going tonight?', 5), { 'where', 'going', 'tonight' })


class RefineFormulaTest(FilmTest):
    def test_finds_speed_and_offset(self):
        # lines exactly over speech, so the best overlap is the right answer
        video = makeSubtitles(self.speech, lead=0.0, tail=0.0)
        subs = times(mistime(video, SPEED, OFFSET))
        # matched words give an answer about a second off
        res = t.refineFormula(subs, self.speech, SPEED + 2e-4, OFFSET + 1.2)
        self.assertIsNotNone(res)
        a, b = res
        for f, v in ((subs[0], video[0]), (subs[-1], video[-1])):
            self.assertAlmostEqual(a * f[0] + b, v[0], delta=0.03)

    def test_short_video_speed_found_by_wider_search(self):
        # a 10-minute video with subtitles made for 25 fps on a 23.976 fps
        # video: matched words got the speed 0.5% wrong, right only in the
        # middle; the usual narrow search can't reach the answer
        speed = 25 / (24000 / 1001)
        speech = makeSpeech(600.0, seed=3)
        video = makeSubtitles(speech, lead=0.0, tail=0.0)
        subs = times(mistime(video, speed, OFFSET))
        a0 = speed + 0.005
        b0 = speed * 300 + OFFSET - a0 * 300
        self.assertIsNone(t.refineFormula(subs, speech, a0, b0, t.refineScaleRange))
        res = t.refineFormula(subs, speech, a0, b0)
        self.assertIsNotNone(res)
        a, b = res
        self.assertAlmostEqual(a, speed, places=6)
        for f, v in ((subs[0], video[0]), (subs[-1], video[-1])):
            self.assertAlmostEqual(a * f[0] + b, v[0], delta=0.02)

    def test_long_film_speed_not_snapped(self):
        # a film's own speech pins the speed precisely: a speed close to a
        # frame rate conversion (0.03% off it) stays as it is
        speed = 24 / 25 * 1.0003
        video = makeSubtitles(self.speech, lead=0.0, tail=0.0)
        subs = times(mistime(video, speed, OFFSET))
        a, b = t.refineFormula(subs, self.speech, speed + 2e-4, OFFSET + 1.2)
        self.assertAlmostEqual(a, speed, delta=2e-5)

    def test_wider_search_refuses_other_speeds(self):
        # in a short video only a frame rate conversion is believed (speech
        # overlap is too flat to tell a speed close to the words' one)
        speed = 1.0083
        speech = makeSpeech(600.0, seed=3)
        video = makeSubtitles(speech, lead=0.0, tail=0.0)
        subs = times(mistime(video, speed, OFFSET))
        a0 = speed + 0.005
        b0 = speed * 300 + OFFSET - a0 * 300
        self.assertIsNone(t.refineFormula(subs, speech, a0, b0))

    def test_short_video_split_to_more_chunks(self):
        self.assertEqual(t.chunkCount(7200.0), 24)
        self.assertEqual(t.chunkCount(734.0), 4)
        self.assertEqual(t.chunkCount(400.0), 3)
        self.assertEqual(t.chunkCount(60.0), 1)

    def test_refuses_far_answer(self):
        # 10 s off: outside the searched range, speech must not confirm it
        res = t.refineFormula(times(self.file), self.speech, SPEED, OFFSET + 10.0)
        self.assertIsNone(res)

    def test_refuses_unrelated_subtitles(self):
        other = times(makeSubtitles(makeSpeech(3600.0, seed=99)))
        self.assertIsNone(t.refineFormula(other, self.speech, 1.0, 0.0))


class ChecksTest(FilmTest):
    """Per-part word check and region check: right formula passes, subtitles
    of a different cut are refused."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # subtitles made for a version with a 45 s scene added in the middle
        cls.cutFile = mistime(cut(cls.video, 1800.0, 45.0), SPEED, OFFSET)
        # transcribed parts: 12 lines from 5 places in the video, slightly off
        cls.chunks = []
        for pos in (0.05, 0.3, 0.5, 0.7, 0.95):
            first = int(pos * (len(cls.video) - 12))
            cls.chunks.append([ (s + 0.3, e + 0.3, text)
                for s, e, text in cls.video[first:first + 12] ])

    def test_chunks_agree(self):
        self.assertTrue(t.checkChunks(self.file, self.chunks, SPEED, OFFSET))

    def test_chunks_refuse_cut(self):
        self.assertFalse(t.checkChunks(self.cutFile, self.chunks, SPEED, OFFSET))

    def test_chunks_need_two_opinions(self):
        self.assertFalse(t.checkChunks(self.file, self.chunks[:1], SPEED, OFFSET))

    def test_short_video_small_chunks_judged_together(self):
        # parts with fewer than checkMinLines lines (e.g. after stretched
        # lines were left out) still count together in a short video
        video = [ l for l in self.video if l[0] < 1200.0 ]
        chunks = []
        for pos in (0.1, 0.35, 0.6, 0.85):
            first = int(pos * (len(video) - 6))
            chunks.append([ (s + 0.3, e + 0.3, text if no < 2 else 'mumble')
                for no, (s, e, text) in enumerate(video[first:first + 6]) ])
        self.assertTrue(t.checkChunks(mistime(video, SPEED, OFFSET), chunks, SPEED, OFFSET))
        self.assertFalse(t.checkChunks(self.file, chunks, SPEED, OFFSET))

    def test_stretched_lines_left_out(self):
        # Whisper line spanning a song: 75 s for text read in 4 s, timed
        # 70 s before its words; normal and slowly sung lines stay
        text = "I've committed a terrible sin in a previous life"
        self.assertTrue(t.isStretched(3609.1, 3684.1, text))
        self.assertFalse(t.isStretched(3380.4, 3386.4, text))
        self.assertFalse(t.isStretched(100.0, 112.0, 'Moanin low, my sweet man'))
        path = os.path.join(tempfile.mkdtemp(prefix='subsync-test-'), 'chunk-000.srt')
        try:
            t.writeSrt(path, [ (3380.7, 3386.4, 'I think basically as a king'),
                               (3609.4, 3684.1, text) ])
            self.assertEqual([ l[2] for l in t.readChunk(path) ], [ 'I think basically as a king' ])
        finally:
            os.remove(path)
            os.rmdir(os.path.dirname(path))

    def test_short_video_chunks_judged_together(self):
        # 4 parts of a short video with only 2 recognizable lines each: too
        # few on their own, enough together (in a long film, never pooled)
        video = [ l for l in self.video if l[0] < 1200.0 ]
        chunks = []
        for pos in (0.1, 0.35, 0.6, 0.85):
            first = int(pos * (len(video) - 12))
            chunks.append([ (s + 0.3, e + 0.3, text if no < 2 else 'mumble')
                for no, (s, e, text) in enumerate(video[first:first + 12]) ])
        short = mistime(video, SPEED, OFFSET)
        self.assertTrue(t.checkChunks(short, chunks, SPEED, OFFSET))
        self.assertFalse(t.checkChunks(self.file, chunks, SPEED, OFFSET))

    def japanese(self):
        """Japanese subtitles, a different-cut copy, and transcribed parts
        worded slightly differently."""
        rnd = random.Random(5)
        video = makeSubtitles(self.speech, japanese=True)
        chunks = []
        for pos in (0.05, 0.3, 0.5, 0.7, 0.95):
            first = int(pos * (len(video) - 12))
            chunks.append([ (s + 0.3, e + 0.3, reword(text, rnd))
                for s, e, text in video[first:first + 12] ])
        return (mistime(video, SPEED, OFFSET),
                mistime(cut(video, 1800.0, 45.0), SPEED, OFFSET), chunks)

    def test_japanese_chunks_agree(self):
        file, _, chunks = self.japanese()
        self.assertTrue(t.checkChunks(file, chunks, SPEED, OFFSET, ngrams=3))

    def test_japanese_chunks_refuse_cut(self):
        _, cutFile, chunks = self.japanese()
        self.assertFalse(t.checkChunks(cutFile, chunks, SPEED, OFFSET, ngrams=3))

    def test_japanese_needs_letter_groups(self):
        # without letter groups nothing matches, so nothing is ever confirmed
        file, _, chunks = self.japanese()
        self.assertFalse(t.checkChunks(file, chunks, SPEED, OFFSET))

    def test_regions_agree(self):
        self.assertTrue(t.checkRegions(times(self.file), self.speech, SPEED, OFFSET))

    def test_regions_refuse_cut(self):
        self.assertFalse(t.checkRegions(times(self.cutFile), self.speech, SPEED, OFFSET))


class PiecewiseTest(FilmTest):
    """Pieces are fitted by speech overlap, so lines exactly over speech are
    used to know the right answer (lines shown longer than speech fit about
    0.1 s off, which leadShift corrects afterwards)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.exact = makeSubtitles(cls.speech, lead=0.0, tail=0.0)

    def test_cut_is_aligned_in_two_pieces(self):
        cutFile = times(mistime(cut(self.exact, 1800.0, 45.0), SPEED, OFFSET))
        offsets = t.alignPiecewise(cutFile, self.speech, SPEED, OFFSET)
        self.assertIsNotNone(offsets)
        pieces = sorted(set(round(o, 1) for o in offsets))
        self.assertEqual(len(pieces), 2)
        self.assertAlmostEqual(pieces[1] - pieces[0], 45.0, delta=0.2)
        err = offsetErrors(cutFile, self.exact, SPEED, offsets)
        self.assertGreaterEqual(sum(e <= 0.1 for e in err) / len(err), 0.98, 'lines within 0.1 s')

    def test_normal_file_stays_one_piece(self):
        file = times(mistime(self.exact, SPEED, OFFSET))
        offsets = t.alignPiecewise(file, self.speech, SPEED, OFFSET)
        self.assertEqual(len(set(round(o, 1) for o in offsets)), 1)
        err = offsetErrors(file, self.exact, SPEED, offsets)
        self.assertGreaterEqual(sum(e <= 0.1 for e in err) / len(err), 0.99)

    def test_pieces_then_lead_correction(self):
        # real subtitles: lines shown before and after speech; pieces plus
        # the lead correction must land on the right timing
        cutFile = times(mistime(cut(self.video, 1800.0, 45.0), SPEED, OFFSET))
        offsets = t.alignPiecewise(cutFile, self.speech, SPEED, OFFSET)
        mapped = [ (SPEED * s + o, SPEED * e + o) for (s, e), o in zip(cutFile, offsets) ]
        shift = t.leadShift(mapped, self.speech)
        err = offsetErrors(cutFile, self.video, SPEED, [ o + shift for o in offsets ])
        self.assertGreaterEqual(sum(e <= 0.1 for e in err) / len(err), 0.95)


class LeadTest(FilmTest):
    """Lines are moved to start `leadTarget` before speech."""

    def shift(self, lead, count=None):
        lines = times(makeSubtitles(self.speech, lead=lead))
        return t.leadShift(lines[:count] if count else lines, self.speech)

    def test_already_right(self):
        self.assertAlmostEqual(self.shift(t.leadTarget), 0.0, delta=0.02)

    def test_late_lines_move_earlier(self):
        self.assertAlmostEqual(self.shift(0.1), 0.1 - t.leadTarget, delta=0.02)
        self.assertAlmostEqual(self.shift(0.0), -t.leadTarget, delta=0.02)

    def test_target_for_english_audio(self):
        lines = times(makeSubtitles(self.speech, lead=0.25))
        self.assertAlmostEqual(t.leadShift(lines, self.speech, t.leadTargetEnglish),
                0.25 - t.leadTargetEnglish, delta=0.02)
        self.assertLess(t.leadTargetEnglish, t.leadTarget,
                'English-language subtitles start closer to speech')

    def test_too_few_lines(self):
        self.assertEqual(self.shift(0.1, count=20), 0.0)

    def test_implausible_shift_refused(self):
        self.assertEqual(self.shift(t.leadTarget + t.leadMaxShift + 0.15), 0.0)


class LanguageTest(unittest.TestCase):
    def test_supports(self):
        self.assertTrue(t.supports('jpn'))
        self.assertTrue(t.supports('JPN'))
        self.assertFalse(t.supports('eng'))
        self.assertFalse(t.supports(None))

    def test_translates_only_for_english_subtitles(self):
        self.assertTrue(t.translates('jpn', 'eng'))
        self.assertFalse(t.translates('jpn', 'pol'))
        self.assertFalse(t.translates('eng', 'eng'))


class CacheDirTest(unittest.TestCase):
    def test_key(self):
        with tempfile.NamedTemporaryFile(delete=False) as fp:
            fp.write(b'video')
        try:
            a = t.getCacheDir(fp.name, 1, 'jpn', translate=True)
            self.assertEqual(a, t.getCacheDir(fp.name, 1, 'jpn', translate=True))
            self.assertNotEqual(a, t.getCacheDir(fp.name, 1, 'jpn', translate=False))
            self.assertNotEqual(a, t.getCacheDir(fp.name, 2, 'jpn', translate=True))
            self.assertNotEqual(a, t.getCacheDir(fp.name, 1, 'kor', translate=True))
            self.assertTrue(a.endswith('.en'))
        finally:
            os.remove(fp.name)

    def test_model_folder_counts_as_installed(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertTrue(t.isModelInstalled(tmp))


if __name__ == '__main__':
    unittest.main()


try:
    import av
    import numpy as np
except ImportError:
    av = None


@unittest.skipIf(av is None, 'PyAV not installed')
class ChannelsTest(unittest.TestCase):
    """Whisper listens only to the chosen channels, like SubSync's own speech
    recognition does: dialogue in the center channel of 5.1 audio, music and
    effects in the others."""

    @classmethod
    def setUpClass(cls):
        rate, seconds = t.sampleRate, 6
        rnd = np.random.default_rng(7)
        n = rate * seconds
        # "dialogue": 440 Hz bursts every other second, center channel only
        tone = 0.3 * np.sin(2 * np.pi * 440 * np.arange(n) / rate)
        cls.dialogue = tone * (np.arange(n) // rate % 2 == 0)
        noise = 0.3 * rnd.standard_normal((6, n)).clip(-3, 3) / 3
        noise[2] = cls.dialogue                 # FL FR FC LFE BL BR
        cls.folder = tempfile.mkdtemp(prefix='subsync-test-')
        cls.path = os.path.join(cls.folder, 'surround.wav')
        with av.open(cls.path, 'w') as out:
            stream = out.add_stream('pcm_s16le', rate=rate, layout='5.1')
            frame = av.AudioFrame.from_ndarray(
                    (noise * 32767).astype(np.int16).T.reshape(1, -1), format='s16', layout='5.1')
            frame.sample_rate = rate
            for packet in stream.encode(frame):
                out.mux(packet)
            for packet in stream.encode(None):
                out.mux(packet)

    @classmethod
    def tearDownClass(cls):
        os.remove(cls.path)
        os.rmdir(cls.folder)

    def similarity(self, audio):
        n = min(len(audio), len(self.dialogue))
        a, b = audio[:n], self.dialogue[:n]
        return float(np.dot(a, b) / np.sqrt(np.dot(a, a) * np.dot(b, b)))

    def test_center_channel_only(self):
        audio = t.decodeRange(self.path, channels=['FC'])
        self.assertGreater(self.similarity(audio), 0.99)

    def test_all_channels_by_default(self):
        audio = t.decodeRange(self.path)
        self.assertLess(self.similarity(audio), 0.9)

    def test_missing_channel_means_all(self):
        audio = t.decodeRange(self.path, channels=['SL'])
        self.assertLess(self.similarity(audio), 0.9)

    def test_part_of_the_audio(self):
        audio = t.decodeRange(self.path, start=2.0, end=3.0, channels=['FC'])
        self.assertEqual(len(audio), t.sampleRate)
        n = t.sampleRate
        a, b = audio, self.dialogue[2 * n:3 * n]
        self.assertGreater(float(np.dot(a, b) / np.sqrt(np.dot(a, a) * np.dot(b, b))), 0.99)

    def test_speech_only(self):
        # speech detection without transcription (to polish the original
        # method's result) is kept like transcripts' plan, and reused
        out = tempfile.mkdtemp(prefix='subsync-test-')
        try:
            speech = t.planSpeech(self.path, out, channels=['FC'])
            self.assertIsInstance(speech, list)
            self.assertEqual(t.loadSpeech(out), speech)
            self.assertAlmostEqual(t.loadPlan(out)[-1][1], 6.0, delta=0.01)
            self.assertFalse(any(name.startswith('chunk-') for name in os.listdir(out)))
            mtime = os.path.getmtime(os.path.join(out, 'plan.json'))
            t.planSpeech(self.path, out, channels=['FC'])
            self.assertEqual(os.path.getmtime(os.path.join(out, 'plan.json')), mtime)
        finally:
            for name in os.listdir(out):
                os.remove(os.path.join(out, name))
            os.rmdir(out)

    def test_chunks_and_cache(self):
        self.assertNotEqual(t.getCacheDir(self.path, None, 'jpn'),
                t.getCacheDir(self.path, None, 'jpn', channels=['FC']))
        chunks = t.planChunks(self.path, speech=[], channels=['FC'])
        self.assertAlmostEqual(chunks[-1][1], 6.0, delta=0.01)


try:
    import faster_whisper
except ImportError:
    faster_whisper = None


@unittest.skipIf(faster_whisper is None, 'faster-whisper not installed')
class FasterWhisperTest(unittest.TestCase):
    """transcribe.py uses some of faster-whisper's internals; a new version of
    it must still have them, or model download and speech detection break."""

    def parameters(self, func):
        import inspect
        return inspect.signature(func).parameters

    def test_model_download(self):
        from faster_whisper.utils import _MODELS, download_model
        self.assertIn(t.defaultModel(), _MODELS)
        for name in ('revision', 'local_files_only'):
            self.assertIn(name, self.parameters(download_model))
        self.assertIn('revision', self.parameters(faster_whisper.WhisperModel.__init__))

    def test_speech_detection(self):
        from faster_whisper.vad import VadOptions, get_speech_timestamps  # noqa: F401
        VadOptions(min_silence_duration_ms=300, speech_pad_ms=0)

    def test_transcription_options(self):
        params = self.parameters(faster_whisper.WhisperModel.transcribe)
        for name in ('language', 'task', 'beam_size', 'vad_filter',
                'condition_on_previous_text', 'word_timestamps'):
            self.assertIn(name, params)
        params = self.parameters(faster_whisper.WhisperModel.detect_language)
        for name in ('vad_filter', 'language_detection_segments'):
            self.assertIn(name, params)
