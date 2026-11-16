"""End-to-end test on a full-length, music-heavy film anyone can rerun: sync
subtitles of Sita Sings the Blues (Nina Paley, 2008, public domain since
2013, sitasingstheblues.com) through the packaged SubSync, and score song
lines and dialogue separately.

About a third of the lines are song lyrics (1920s records by Annette
Hanshaw), which tests speech detection on singing; the film is 82 minutes,
which tests the path of long films (5-minute parts, early stop, region
checks) that the 12-minute Tears of Steel test doesn't reach.

The film is the YouTube upload the community subtitles on Amara were timed
on, archived at archive.org/details/youtube-RzTg7YXuy34; subtitles come from
Amara (English, Spanish, Chinese, French) and archive.org (Czech) at run time,
nothing is stored in this repository. A copy of every file is mistimed with a
known error (speed x1.04271 plus 9.4 s) and synced to the film's English
audio, without being told the audio language.

    English subtitles   original SubSync method (pocketsphinx)
    other languages     translated to English for matching (route PIVOT)

French is shown but doesn't fail the test (--report-only): its lines are
timed about 0.3 s later than SubSync's start-of-speech target, all of them,
so the whole file moves by that much (a timing style, not a sync error).

usage:
    python tests/e2e/sita_sings_the_blues.py --app dist/subsync/subsync-cmd.exe --data DIR
        [--work DIR] [--langs en,es,zh,cs,fr] [--min-within 80] [--report-only fr] [--download]
"""

import argparse
import glob
import json
import os
import re
import statistics
import subprocess
import sys
import tempfile
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tears_of_steel import parseTime, writeSrt, compare     # noqa: E402

VIDEO = 'RzTg7YXuy34.mp4'
VIDEO_URL = 'https://archive.org/download/youtube-RzTg7YXuy34/RzTg7YXuy34.mp4'
LENGTH = 4891.25    # seconds of audio
AMARA = 'https://amara.org/api/videos/YkwgVDEZTA0g/languages/{}/subtitles/?format=srt'
SUBS = {
        'en': ('eng', AMARA.format('en')),
        'es': ('spa', AMARA.format('es')),
        'zh': ('chi', AMARA.format('zh-tw')),
        'fr': ('fre', AMARA.format('fr')),
        'cs': ('cze', 'https://archive.org/download/SitaSingsTheBluesCsSubtitles/Sita_Sings_the_Blues_CS_UTF-8.srt'),
        }

SPEED, OFFSET = 1.04271, 9.4

# the songs, in seconds of the film (each ends with Hanshaw's spoken "That's
# all!"), plus the children's chant; lines starting in them are song lines
SONGS = [ (75.6, 113.0), (703.0, 872.7), (1160.6, 1324.0), (1669.8, 1836.2),
          (1999.0, 2167.2), (2392.6, 2575.3), (2722.7, 2874.4), (3425.3, 3621.1),
          (3724.7, 3876.4), (3913.2, 3979.8), (4103.6, 4256.1), (4385.6, 4549.1) ]


def isSong(t):
    return any(a <= t <= b for a, b in SONGS)


def readSrt(path):
    """Lines of an SRT file, also with a blank line after the timestamp (as
    some Amara exports have)."""
    rows = open(path, encoding='utf-8-sig').read().replace('\r', '').split('\n')
    stamps = [ i for i, r in enumerate(rows) if ' --> ' in r ]
    lines = []
    for k, i in enumerate(stamps):
        end = stamps[k + 1] - 1 if k + 1 < len(stamps) else len(rows)
        text = '\n'.join(r for r in rows[i + 1:end] if r.strip())
        a, b = rows[i].split(' --> ')
        if text:
            lines.append((parseTime(a), parseTime(b), text))
    return sorted(lines)


def download(data, langs):
    os.makedirs(data, exist_ok=True)
    files = [ (VIDEO_URL, VIDEO) ] + [ (SUBS[l][1], 'sita-{}.srt'.format(l)) for l in langs ]
    for url, name in files:
        path = os.path.join(data, name)
        if not os.path.exists(path):
            print('downloading', url, flush=True)
            req = urllib.request.Request(url, headers={ 'User-Agent': 'subsync-e2e-test' })
            with urllib.request.urlopen(req) as src, open(path + '.part', 'wb') as dst:
                while True:
                    chunk = src.read(1 << 20)
                    if not chunk:
                        break
                    dst.write(chunk)
            os.replace(path + '.part', path)


def speechOverSongs():
    """Share of song time detected as speech, from the newest transcript
    cache of this film (its chunks end at the film's length)."""
    plans = []
    for path in glob.glob(os.path.join(tempfile.gettempdir(), 'subsync-transcripts', '*', 'plan.json')):
        try:
            plan = json.load(open(path))
            if plan.get('speech') and abs(plan['chunks'][-1][1] - LENGTH) < 5.0:
                plans.append((os.path.getmtime(path), plan['speech']))
        except (OSError, ValueError, KeyError, IndexError):
            pass
    if not plans:
        return None
    speech = max(plans)[1]
    song = sum(max(0.0, min(b, e) - max(a, s)) for a, b in SONGS for s, e in speech)
    total = sum(b - a for a, b in SONGS)
    return 100 * song / total


def stats(err, n):
    if not n:
        return '- | -', 100.0
    within = 100 * sum(abs(e) <= 0.2 for e in err) / n
    worst = max(map(abs, err)) if err else float('inf')
    return '{:.1f}% of {} | {:.2f} s'.format(within, n, worst), within


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--app', required=True, help='subsync-cmd of the package, or "python run.py"')
    parser.add_argument('--data', required=True, help='folder with the film and its subtitles')
    parser.add_argument('--work', default='e2e-sita', help='folder for mistimed copies and results')
    parser.add_argument('--langs', default='en,es,zh,cs,fr')
    parser.add_argument('--report-only', default='fr',
            help='languages shown but not failing the test')
    parser.add_argument('--min-within', type=float, default=80.0,
            help='fail when fewer song or dialogue lines are within 0.2 s (percent)')
    parser.add_argument('--download', action='store_true', help='download missing files first')
    args = parser.parse_args()

    langs = args.langs.split(',')
    reportOnly = set(args.report_only.split(',')) if args.report_only else set()
    if args.download:
        download(args.data, langs)
    os.makedirs(args.work, exist_ok=True)
    video = os.path.abspath(os.path.join(args.data, VIDEO))
    app = [ os.path.abspath(x) if os.path.exists(x) else x for x in args.app.split() ]
    rows, failed, speechShare = [], False, None

    for lang in langs:
        truth = readSrt(os.path.join(args.data, 'sita-{}.srt'.format(lang)))
        sub = os.path.abspath(os.path.join(args.work, 'sita-{}.mistimed.srt'.format(lang)))
        out = os.path.abspath(os.path.join(args.work, 'sita-{}.synced.srt'.format(lang)))
        log = os.path.abspath(os.path.join(args.work, 'sita-{}.log'.format(lang)))
        writeSrt(sub, [ ((s - OFFSET) / SPEED, (e - OFFSET) / SPEED, x) for s, e, x in truth ])
        for path in (out, log):
            if os.path.exists(path):
                os.remove(path)

        start = time.time()
        subprocess.run(app + [ '--cli', '--loglevel=INFO', '--logfile=' + log, 'sync',
                '--sub', sub, '--sub-lang=' + SUBS[lang][0], '--ref', video,
                '--ref-stream-by-type=audio', '--out', out, '--overwrite' ],
                stdin=subprocess.DEVNULL)
        took = time.time() - start

        logText = open(log, encoding='utf-8', errors='replace').read() if os.path.exists(log) else ''
        route = ', then '.join(re.findall(r'matching route: (\w+)', logText)) or 'original'
        name = lang + (' (timing style)' if lang in reportOnly else '')
        if not os.path.exists(out):
            rows.append('| {} | {} | {:.0f} s | no file saved | | | |'.format(name, route, took))
            failed = failed or lang not in reportOnly
            continue
        if 'pivot' in route and speechShare is None:
            speechShare = speechOverSongs()

        # pair lines by text, then split them into song and other lines
        songTruth = [ t for t in truth if isSong(t[0]) ]
        otherTruth = [ t for t in truth if not isSong(t[0]) ]
        synced = readSrt(out)
        songErr, _ = compare(songTruth, synced)
        otherErr, _ = compare(otherTruth, synced)
        song, songWithin = stats(songErr, len(songTruth))
        other, otherWithin = stats(otherErr, len(otherTruth))
        rows.append('| {} | {} | {:.0f} s | {} | {} |'.format(name, route, took, song, other))
        if lang not in reportOnly and min(songWithin, otherWithin) < args.min_within:
            failed = True

    report = [ '### Sita Sings the Blues, end to end', '',
        'Full-length (82 min), music-heavy film: subtitles mistimed by x1.04271 plus 9.4 s, '
        'synced by the packaged SubSync and scored against their own timing.', '',
        '| Subtitles | Method | Time | Song lines within 0.2 s | Worst song line | '
        'Other lines within 0.2 s | Worst other line |',
        '|---|---|---|---|---|---|---|' ] + rows
    if speechShare is not None:
        report += [ '', 'Singing detected as speech: {:.0f}% of the song time.'.format(speechShare) ]
    report = '\n'.join(report)
    print(report)
    summary = os.environ.get('GITHUB_STEP_SUMMARY')
    if summary:
        with open(summary, 'a', encoding='utf-8') as fp:
            fp.write(report + '\n')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
