"""Which method matches subtitles with the reference, per language pair.

    ORIGINAL     original SubSync: pocketsphinx speech recognition (or another
                 subtitle file as reference), words matched directly or
                 through a dictionary
    ENGLISH      English subtitles, audio in a language without a pocketsphinx
                 model: Whisper translates the speech to English
    SAME         subtitles in the language of the audio (no pocketsphinx
                 model): Whisper writes the speech down in that language
    PIVOT        any other pair, including English audio: speech goes to
                 English with Whisper, subtitles are machine-translated to
                 English just for matching (see translate.py)
    DICTIONARY   like SAME, but subtitles in another language are matched
                 through SubSync's dictionaries (when translation can't be used)
"""

from subsync.synchro import transcribe, translate
from subsync.data import languages

ORIGINAL = 'original'
ENGLISH = 'english'
SAME = 'same'
PIVOT = 'pivot'
DICTIONARY = 'dictionary'

WHISPER = (ENGLISH, SAME, PIVOT, DICTIONARY)


def code2(lang):
    """2-letter code of a 3-letter one, `None` when unknown."""
    return lang and languages.get(lang.lower()).code2


def canTranslate(subLang):
    """Subtitles in this language (3-letter code) can be translated to
    English for matching."""
    return translate.isAvailable() and translate.supports(code2(subLang))


def getRoute(sub, ref):
    """Method for synchronizing `sub` with `ref` (input streams)."""
    if not ref or ref.type != 'audio' or not ref.lang:
        return ORIGINAL

    refLang = ref.lang.lower()
    subLang = sub.lang.lower() if sub and sub.lang else None
    whisperOnly = transcribe.supports(refLang)

    if whisperOnly and subLang == 'eng':
        return ENGLISH
    if whisperOnly and (not subLang or subLang == refLang):
        return SAME
    if subLang and subLang not in (refLang, 'eng') and (whisperOnly or refLang == 'eng') \
            and transcribe.isAvailable() and canTranslate(subLang):
        return PIVOT
    if whisperOnly:
        return DICTIONARY
    return ORIGINAL


def matchLanguage(route, sub):
    """Language subtitle words are matched in."""
    return 'eng' if route == PIVOT else (sub.lang if sub else None)


def transcriptLanguage(route, ref):
    """Language of Whisper's text, see transcribe.getTranscriptChunks."""
    return 'eng' if route in (ENGLISH, PIVOT) else ref.lang


def translatesSpeech(route, ref):
    """Whisper translates the speech to English (instead of writing it down
    in the spoken language)."""
    return route in (ENGLISH, PIVOT) and ref.lang.lower() != 'eng'
