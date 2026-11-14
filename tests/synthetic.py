"""Synthetic films for tests: detected speech and subtitles with known timing.

Real films can't be part of the repository, so the alignment functions are
tested on made-up speech (talking and pauses of random length, with longer
breaks for music) and subtitles generated from it, then deliberately mistimed
with a known speed and offset.
"""

import os
import random
import string
import sys

# transcribe.py imports nothing from SubSync, it is loaded on its own so tests
# don't need the compiled engine
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'subsync', 'synchro'))
import transcribe  # noqa: E402


def makeSpeech(duration=3600.0, seed=1):
    """Speech (start, end) segments: talking 0.6-3.5 s, pauses mostly
    0.4-3 s, sometimes 8-40 s (music, action)."""
    rnd = random.Random(seed)
    speech, t = [], 20.0
    while t < duration - 10.0:
        length = rnd.uniform(0.6, 3.5)
        speech.append((round(t, 2), round(t + length, 2)))
        t += length + (rnd.uniform(8.0, 40.0) if rnd.random() < 0.05
                else rnd.uniform(0.4, 3.0))
    return speech


# kana and common kanji, for text written without spaces like Japanese
JAPANESE = ('あいうえおかきくけこさしすせそたちつてとなにぬねのはひふへほまみむめも'
        'やゆよらりるれろわをんアイウエオカキクケコサシスセソタチツテト'
        '今日明行来見話人時間家車雨空夜朝花水火山川先生学校友達')


def makeSubtitles(speech, lead=0.25, tail=0.8, seed=2, japanese=False):
    """One subtitle line per speech segment: shown `lead` seconds before the
    speech starts and `tail` after it ends (but never over the next line),
    with a few random words of text (or Japanese-like text without spaces)."""
    rnd = random.Random(seed)
    lines = []
    for no, (start, end) in enumerate(speech):
        begin, finish = start - lead, end + tail
        if no + 1 < len(speech):
            finish = min(finish, speech[no + 1][0] - lead - 0.05)
        if japanese:
            text = ''.join(rnd.choice(JAPANESE) for _ in range(rnd.randint(8, 16))) + '。'
        else:
            text = ' '.join(''.join(rnd.choice(string.ascii_lowercase) for _ in range(6))
                    for _ in range(rnd.randint(3, 6)))
        lines.append((begin, max(finish, begin + 0.5), text))
    return lines


def reword(text, rnd):
    """Text as speech recognition would give it: one letter different and
    punctuation changed, like a transcript of the same line."""
    letters = [ c for c in text if c not in '。、？！' ]
    pos = rnd.randrange(len(letters))
    letters[pos] = rnd.choice(JAPANESE)
    return ''.join(letters[:len(letters) // 2]) + '、' + ''.join(letters[len(letters) // 2:])


def mistime(lines, a, b):
    """Subtitle file times for lines that are right in the video, when the
    file is off by speed `a` and offset `b` (video time = a * file time + b)."""
    return [ ((start - b) / a, (end - b) / a) + tuple(rest)
            for start, end, *rest in lines ]


def cut(lines, at, length):
    """Lines of a different cut: a scene of `length` seconds was added at
    time `at`, so every later line comes `length` seconds later."""
    return [ (start + length, end + length) + tuple(rest) if start >= at
            else (start, end) + tuple(rest) for start, end, *rest in lines ]


def times(lines):
    return [ (start, end) for start, end, *_ in lines ]
