"""End-to-end test anyone can rerun: sync the official subtitles of Tears of
Steel, a free film by the Blender Foundation (CC-BY 3.0, mango.blender.org),
through the packaged SubSync, and score the result line by line.

For every subtitle language, a copy is mistimed with a known error (a
frame-rate mismatch, 25 fps subtitles on a 23.976 fps film, plus 2.5 s), then
SubSync syncs it to the film's English audio, without being told the audio
language. The official timing is the answer key.

    English subtitles   original SubSync method (pocketsphinx), which finds
                        too few words in this film, then Whisper writes the
                        English speech down (route SAME)
    other languages     translated to English for matching (route PIVOT)

usage:
    python tests/e2e/tears_of_steel.py --app dist/subsync/subsync-cmd.exe --data DIR
        [--work DIR] [--langs en,es,de,it,nl,ru] [--min-within 80] [--report-only LANGS]

DIR holds tears_of_steel_720p.mov and TOS-<lang>.srt (downloaded by --download).
Writes a Markdown table to $GITHUB_STEP_SUMMARY when set. Exit code 1 when a
language has fewer lines within 0.2 s than --min-within percent. Languages in
--report-only are shown but don't fail the test.
"""

import argparse
import os
import re
import statistics
import subprocess
import sys
import time
import urllib.request

VIDEO_URL = 'https://download.blender.org/demo/movies/ToS/tears_of_steel_720p.mov'
SUBS_URL = 'https://download.blender.org/demo/movies/ToS/subtitles/TOS-{}.srt'
VIDEO = 'tears_of_steel_720p.mov'

# (the French file on blender.org is a joke translation, Norwegian is empty)
LANGUAGES = { 'en': 'eng', 'es': 'spa', 'de': 'ger', 'it': 'ita',
        'nl': 'dut', 'ru': 'rus' }

# known error: subtitles made for 25 fps shown on the 23.976 fps film, 2.5 s late
SPEED, OFFSET = 25 / 23.976, 2.5

TIME = re.compile(r'(\d+):(\d+):(\d+)[,.](\d+)')


def parseTime(text):
    h, m, s, ms = map(int, TIME.match(text.strip()).groups())
    return h * 3600 + m * 60 + s + ms / 1000


def formatTime(t):
    ms = max(int(round(t * 1000)), 0)
    return '{:02}:{:02}:{:02},{:03}'.format(ms // 3600000, ms // 60000 % 60, ms // 1000 % 60, ms % 1000)


def readSrt(path):
    text = open(path, encoding='utf-8-sig').read().replace('\r', '')
    lines = []
    for block in text.split('\n\n'):
        rows = block.strip().split('\n')
        i = next((k for k, row in enumerate(rows) if ' --> ' in row), None)
        if i is None or i + 1 >= len(rows):
            continue
        start, end = rows[i].split(' --> ')
        lines.append((parseTime(start), parseTime(end), '\n'.join(rows[i + 1:])))
    return sorted(lines)


def compare(truth, synced):
    """Start time errors (seconds) of synced lines against the official ones,
    and the number of official lines missing from the result. SubSync changes
    only timing, so lines are paired by their text, in order."""
    import difflib
    key = lambda text: ' '.join(text.split())
    matcher = difflib.SequenceMatcher(None, [ key(t) for _, _, t in truth ],
            [ key(t) for _, _, t in synced ], autojunk=False)
    err = []
    for block in matcher.get_matching_blocks():
        for k in range(block.size):
            err.append(synced[block.b + k][0] - truth[block.a + k][0])
    return err, len(truth) - len(err)


def writeSrt(path, lines):
    with open(path, 'w', encoding='utf-8', newline='\n') as fp:
        for no, (start, end, text) in enumerate(lines, 1):
            fp.write('{}\n{} --> {}\n{}\n\n'.format(no, formatTime(start), formatTime(end), text))


def download(data):
    os.makedirs(data, exist_ok=True)
    files = [ (VIDEO_URL, VIDEO) ] + [ (SUBS_URL.format(l), 'TOS-{}.srt'.format(l)) for l in LANGUAGES ]
    for url, name in files:
        path = os.path.join(data, name)
        if not os.path.exists(path):
            print('downloading', url, flush=True)
            urllib.request.urlretrieve(url, path + '.part')
            os.replace(path + '.part', path)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--app', required=True, help='subsync-cmd of the package, or "python run.py"')
    parser.add_argument('--data', required=True, help='folder with the film and its subtitles')
    parser.add_argument('--work', default='e2e-work', help='folder for mistimed copies and results')
    parser.add_argument('--langs', default=','.join(LANGUAGES))
    parser.add_argument('--report-only', default='',
            help='languages shown but not failing the test (known limits)')
    parser.add_argument('--min-within', type=float, default=80.0,
            help='fail when fewer lines are within 0.2 s (percent)')
    parser.add_argument('--download', action='store_true', help='download missing files first')
    args = parser.parse_args()

    if args.download:
        download(args.data)
    os.makedirs(args.work, exist_ok=True)
    video = os.path.abspath(os.path.join(args.data, VIDEO))
    rows, failed = [], False
    reportOnly = set(args.report_only.split(',')) if args.report_only else set()

    for lang in args.langs.split(','):
        truth = readSrt(os.path.join(args.data, 'TOS-{}.srt'.format(lang)))
        # subtitle file times for the film's times: film = SPEED * file + OFFSET
        mistimed = [ ((s - OFFSET) / SPEED, (e - OFFSET) / SPEED, x) for s, e, x in truth ]
        sub = os.path.abspath(os.path.join(args.work, 'TOS-{}.mistimed.srt'.format(lang)))
        out = os.path.abspath(os.path.join(args.work, 'TOS-{}.synced.srt'.format(lang)))
        log = os.path.abspath(os.path.join(args.work, 'TOS-{}.log'.format(lang)))
        writeSrt(sub, mistimed)
        for path in (out, log):
            if os.path.exists(path):
                os.remove(path)

        # a relative path to the app is not found on Windows, made absolute
        app = [ os.path.abspath(x) if os.path.exists(x) else x for x in args.app.split() ]
        cmd = app + [ '--cli', '--loglevel=INFO', '--logfile=' + log, 'sync',
                '--sub', sub, '--sub-lang=' + LANGUAGES[lang], '--ref', video,
                '--ref-stream-by-type=audio', '--out', out, '--overwrite' ]
        start = time.time()
        subprocess.run(cmd, stdin=subprocess.DEVNULL)
        took = time.time() - start

        logText = open(log, encoding='utf-8', errors='replace').read() if os.path.exists(log) else ''
        # methods tried, e.g. "original, then same" when Whisper took over
        route = ', then '.join(re.findall(r'matching route: (\w+)', logText)) or 'original'
        if not os.path.exists(out):
            rows.append((lang, route, took, None))
            failed = failed or lang not in reportOnly
            continue
        synced = readSrt(out)
        err, missing = compare(truth, synced)
        if not err:
            err = [ float('inf') ]      # no line of the result is an official one
        # a line missing from the result counts as wrong
        within = 100 * sum(abs(e) <= 0.2 for e in err) / len(truth)
        rows.append((lang, route, took, (len(truth), missing, within,
            statistics.mean(map(abs, err)), statistics.mean(err), max(map(abs, err)))))
        failed = failed or (within < args.min_within and lang not in reportOnly)

    table = [ '| Subtitles | Method | Time | Lines | Within 0.2 s | Average error | Bias | Worst |',
              '|---|---|---|---|---|---|---|---|' ]
    for lang, route, took, res in rows:
        name = lang + (' (known limit)' if lang in reportOnly else '')
        if res is None:
            table.append('| {} | {} | {:.0f} s | no file saved | | | | |'.format(name, route, took))
        else:
            n, missing, within, avg, bias, worst = res
            lines = '{}{}'.format(n, ', {} missing'.format(missing) if missing else '')
            table.append('| {} | {} | {:.0f} s | {} | {:.1f}% | {:.3f} s | {:+.3f} s | {:.2f} s |'.format(
                name, route, took, lines, within, avg, bias, worst))
    report = '\n'.join([ '### Tears of Steel, end to end', '',
        'Official subtitles mistimed as 25 fps on the 23.976 fps film plus 2.5 s, '
        'synced by the packaged SubSync and scored against the official timing.', '' ] + table)
    print(report)
    summary = os.environ.get('GITHUB_STEP_SUMMARY')
    if summary:
        with open(summary, 'a', encoding='utf-8') as fp:
            fp.write(report + '\n')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
