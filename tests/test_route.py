"""Unit tests for choosing the matching method per language pair (route.py)
and for the translation helpers (translate.py).

The route tests need SubSync's compiled engine (they import subsync.synchro),
so they are skipped where it isn't built; the translation test needs the
translation model and is skipped without it.
"""

import os
import unittest

import synthetic  # noqa: F401  (puts subsync/synchro on the path)
import translate

try:
    import builtins
    builtins.__dict__.setdefault('_', lambda s: s)
    from subsync.synchro import route
except ImportError:
    route = None


class Stream(object):
    def __init__(self, lang, type='audio'):
        self.lang, self.type = lang, type


@unittest.skipIf(route is None, 'SubSync engine (gizmo) not built')
class RouteTest(unittest.TestCase):
    def route(self, sub, ref, refType='audio'):
        return route.getRoute(Stream(sub, 'subtitle/text'), Stream(ref, refType))

    def test_english_subtitles_japanese_audio(self):
        self.assertEqual(self.route('eng', 'jpn'), route.ENGLISH)

    def test_same_language(self):
        self.assertEqual(self.route('jpn', 'jpn'), route.SAME)
        self.assertEqual(self.route(None, 'jpn'), route.SAME)

    def test_any_other_pair_goes_through_english(self):
        if not route.canTranslate('spa'):
            self.skipTest('translation not available')
        self.assertEqual(self.route('spa', 'jpn'), route.PIVOT)
        self.assertEqual(self.route('jpn', 'eng'), route.PIVOT, 'English audio, reverse direction')
        self.assertEqual(self.route('pol', 'eng'), route.PIVOT)

    def test_original_method_kept(self):
        self.assertEqual(self.route('eng', 'eng'), route.ORIGINAL)
        self.assertEqual(self.route('eng', 'jpn', refType='subtitle/text'), route.ORIGINAL)
        self.assertEqual(self.route('eng', None), route.ORIGINAL)

    def test_languages_used(self):
        ref, sub = Stream('jpn'), Stream('spa', 'subtitle/text')
        self.assertEqual(route.matchLanguage(route.PIVOT, sub), 'eng')
        self.assertEqual(route.transcriptLanguage(route.PIVOT, ref), 'eng')
        self.assertTrue(route.translatesSpeech(route.PIVOT, ref))
        self.assertFalse(route.translatesSpeech(route.PIVOT, Stream('eng')),
                'English speech is written down, not translated')
        self.assertEqual(route.transcriptLanguage(route.SAME, ref), 'jpn')


class TranslateHelpersTest(unittest.TestCase):
    def test_supports(self):
        self.assertTrue(translate.supports('es'))
        self.assertTrue(translate.supports('JA'))
        self.assertFalse(translate.supports('en'), 'English needs no translation')
        self.assertFalse(translate.supports('xx'))
        self.assertFalse(translate.supports(None))

    def test_clean_text(self):
        self.assertEqual(translate.cleanText('{\\i1}Hola,\\Nmundo <b>ya</b>'), 'Hola, mundo ya')

    def test_cache_path(self):
        a = translate.getCachePath([ 'hola' ], 'es')
        self.assertEqual(a, translate.getCachePath([ 'hola' ], 'es'))
        self.assertNotEqual(a, translate.getCachePath([ 'hola' ], 'pt'))
        self.assertNotEqual(a, translate.getCachePath([ 'hola', 'adiós' ], 'es'))


@unittest.skipUnless(translate._hasModules() and translate.isModelInstalled(),
        'translation model not installed')
class TranslateModelTest(unittest.TestCase):
    def test_translates_to_english(self):
        res = translate.translateLines([ '¿Dónde está la estación?', '', '<i>Gracias</i>.' ], 'es')
        self.assertEqual(len(res), 3)
        self.assertIn('station', res[0].lower())
        self.assertEqual(res[1], '', 'empty lines stay empty')


if __name__ == '__main__':
    unittest.main()
