#!/usr/bin/env python3
"""Runs SubSync Echo's tests with one command, and ends with a summary.

    python tests/run_all.py                 unit tests (seconds)
    python tests/run_all.py e2e             end-to-end tests on two free films
    python tests/run_all.py all             both

The unit tests check the timing logic on synthetic films with known right
answers. They need numpy; more of them run when PyAV, faster-whisper and the
SubSync engine are present (the start of the run says which are).

The end-to-end tests sync deliberately mistimed subtitles of two free films,
Tears of Steel (12 minutes, 6 languages) and Sita Sings the Blues (82 minutes,
many songs, 5 languages), with the real app, and score every line against the
correct timing. They download what's missing into --data: the films and their
subtitles (about 850 MB), and, unless --app is given, the latest release of
SubSync Echo for this system, its SHA-256 checked against the release's
SHA256SUMS or the one GitHub keeps for it (set GITHUB_TOKEN if GitHub's limit
of 60 requests an hour without signing in is reached). The app downloads its
speech and translation models the first time (about 980 MB). On the test
laptop the syncing took about 2 minutes for Tears of Steel and 6 for Sita; a
first run adds the downloads. Later runs reuse everything. Each app tested
keeps its transcripts in its own folder under DATA/temp.

options:
    --app PATH       test this app instead of the latest release, e.g.
                     dist/subsync/subsync-cmd.exe, or "python run.py"
    --release TAG    test this release instead of the latest, e.g. 0.20
    --films LIST     tos, sita or both (default tos,sita)
    --data DIR       downloads and results (default e2e-data)
    --install        first install the unit tests' packages, at the versions
                     the release builds use (.github/constraints.txt)
    -v               list every unit test

See doc/development.md for what each result means.
"""

import argparse
import hashlib
import http.client
import json
import os
import platform
import subprocess
import sys
import tarfile
import time
import unittest
import urllib.error
import urllib.request
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = 'resonaut/SubSync-Echo'
FILMS = {
    'tos': ('Tears of Steel', 'tests/e2e/tears_of_steel.py', 'tears-of-steel'),
    'sita': ('Sita Sings the Blues', 'tests/e2e/sita_sings_the_blues.py', 'sita'),
}
TEST_PACKAGES = ['numpy', 'av', 'faster-whisper']


def say(text=''):
    print(text, flush=True)


def heading(text):
    say()
    say('== ' + text)


def minutes(seconds):
    return '{:.0f} s'.format(seconds) if seconds < 90 else '{:.1f} min'.format(seconds / 60)


# --- unit tests -------------------------------------------------------------

def available(module):
    try:
        mod = __import__(module)
    except Exception:
        return False
    # the gizmo/ source folder imports as an empty package; the built engine
    # is a compiled module with a file
    return module != 'gizmo' or getattr(mod, '__file__', None) is not None


def install():
    heading('Installing the unit tests\' packages')
    if sys.version_info[:2] != (3, 12):
        say('note: the pinned versions are for Python 3.12, the version the releases are '
            'built with; this is Python {}.{}, so pip may not find them.'.format(*sys.version_info[:2]))
    cmd = [sys.executable, '-m', 'pip', 'install', '-c',
           os.path.join(ROOT, '.github', 'constraints.txt')] + TEST_PACKAGES
    return subprocess.call(cmd) == 0


def runUnit(verbose):
    heading('Unit tests')
    parts = [
        ('numpy', 'numpy', 'needed'),
        ('PyAV', 'av', 'audio channel tests'),
        ('faster-whisper', 'faster_whisper', 'checks of the faster-whisper version'),
        ('SubSync engine', 'gizmo', 'matching-method tests (built from source only)'),
    ]
    sys.path.insert(0, ROOT)
    for name, module, use in parts:
        say('  {:<16} {:<13} {}'.format(name, 'found' if available(module) else 'not found', use))
    if not available('numpy'):
        say('\nnumpy is needed: pip install numpy (or run with --install)')
        return False, 'numpy missing'

    tests = os.path.join(ROOT, 'tests')
    sys.path.insert(0, tests)
    suite = unittest.defaultTestLoader.discover(tests, top_level_dir=tests)
    result = unittest.TextTestRunner(verbosity=2 if verbose else 1).run(suite)
    detail = '{} run, {} skipped'.format(result.testsRun, len(result.skipped))
    if not result.wasSuccessful():
        detail += ', {} failed'.format(len(result.failures) + len(result.errors))
    return result.wasSuccessful(), detail


# --- the app ----------------------------------------------------------------

def urlopen(url, headers={}):
    return urllib.request.urlopen(urllib.request.Request(
        url, headers=dict({'User-Agent': 'SubSync-Echo-tests'}, **headers)), timeout=60)


def expectedSha256(base, tag, name):
    """The SHA-256 a release file should have, and where it comes from: the
    release's SHA256SUMS file (from 0.21), or else the one GitHub keeps for
    each release file (through its API, which allows 60 requests an hour
    without signing in, more with GITHUB_TOKEN set)."""
    try:
        sums = urlopen(base + 'SHA256SUMS').read().decode('utf-8')
        for line in sums.splitlines():
            parts = line.split()
            if len(parts) == 2 and parts[1].lstrip('*') == name:
                return parts[0].lower(), 'the release\'s SHA256SUMS'
    except urllib.error.HTTPError as err:
        if err.code != 404:
            raise
    headers = {'Accept': 'application/vnd.github+json'}
    if os.environ.get('GITHUB_TOKEN'):
        headers['Authorization'] = 'Bearer ' + os.environ['GITHUB_TOKEN']
    try:
        release = json.load(urlopen('https://api.github.com/repos/{}/releases/tags/{}'.format(REPO, tag), headers))
    except urllib.error.HTTPError as err:
        return None, 'GitHub\'s API refused ({} {}); set GITHUB_TOKEN or try again later'.format(err.code, err.reason)
    asset = next((a for a in release.get('assets', []) if a['name'] == name), {})
    digest = (asset.get('digest') or '')
    if digest.startswith('sha256:'):
        return digest[len('sha256:'):], 'the SHA-256 GitHub keeps for it'
    return None, 'the release has no SHA256SUMS and GitHub keeps no SHA-256 for it'


def download(url, path, label, tries=3):
    """Downloads url to path. A dropped connection can end a download early
    without an error, so the size received is compared with the size the
    server announced, and a short download is tried again."""
    tmp = path + '.part'
    for attempt in range(1, tries + 1):
        try:
            with urlopen(url) as res, open(tmp, 'wb') as fp:
                total = int(res.headers.get('Content-Length') or 0)
                done, shown = 0, -1
                while True:
                    block = res.read(1 << 20)
                    if not block:
                        break
                    fp.write(block)
                    done += len(block)
                    if total and done * 10 // total != shown:
                        shown = done * 10 // total
                        say('  {} {:3d}% of {:.0f} MB'.format(label, shown * 10, total / 1e6))
            if total and done != total:
                raise IOError('download cut off: {} of {} bytes'.format(done, total))
            os.replace(tmp, path)
            return
        except (IOError, OSError, http.client.HTTPException) as err:
            if os.path.exists(tmp):
                os.remove(tmp)
            if attempt == tries:
                raise RuntimeError('{} could not be downloaded ({}), please run again'.format(label, err))
            say('  {}: {}; trying again'.format(label, err))


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as fp:
        for block in iter(lambda: fp.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def packageSuffix():
    machine = platform.machine().lower()
    if sys.platform == 'win32' and machine in ('amd64', 'x86_64'):
        return '-windows-x64.zip'
    if sys.platform.startswith('linux') and machine in ('x86_64', 'amd64'):
        return '-linux-x86_64.tar.xz'
    return None


def findApp(folder):
    name = 'subsync-cmd.exe' if sys.platform == 'win32' else 'subsync-cmd'
    for top, _, files in os.walk(folder):
        if name in files:
            return os.path.join(top, name)
    return None


def unpack(archive, folder):
    base = os.path.realpath(folder)
    if archive.endswith('.zip'):
        with zipfile.ZipFile(archive) as z:
            z.extractall(folder)    # zipfile keeps every file inside folder
    else:
        with tarfile.open(archive) as t:
            for m in t.getmembers():
                target = os.path.realpath(os.path.join(folder, m.name))
                if target != base and not target.startswith(base + os.sep):
                    raise RuntimeError('unsafe path in archive: ' + m.name)
            if hasattr(tarfile, 'data_filter'):
                t.extractall(folder, filter='data')     # also refuses links leading out
            else:
                t.extractall(folder)


def releaseApp(data, tag):
    """Downloads, checks and unpacks a release of SubSync Echo for this
    system. Returns the path of its command line program, a description of
    the check, and True when the download was checked, None when it couldn't
    be."""
    suffix = packageSuffix()
    if not suffix:
        raise RuntimeError('there is no release package for {} {}; build SubSync Echo from '
                           'source and pass --app'.format(sys.platform, platform.machine()))
    if not tag:
        # the release page link leads to the latest tag; unlike GitHub's API,
        # it has no limit on requests without signing in
        tag = urlopen('https://github.com/{}/releases/latest'.format(REPO)).geturl().rstrip('/').rsplit('/', 1)[-1]
        if tag == 'releases':
            raise RuntimeError('no release found')
    name = 'subsync-{}{}'.format(tag, suffix)
    base = 'https://github.com/{}/releases/download/{}/'.format(REPO, tag)

    folder = os.path.join(data, 'app', tag)
    app = findApp(folder) if os.path.isdir(folder) else None
    if app:
        say('  SubSync Echo {} already unpacked in {}'.format(tag, folder))
        return app, '{}, unpacked by an earlier run'.format(tag), True

    os.makedirs(folder, exist_ok=True)
    archive = os.path.join(data, 'app', name)
    if not os.path.exists(archive):
        download(base + name, archive, name)
    expected, source = expectedSha256(base, tag, name)
    if expected:
        if sha256(archive) != expected:
            os.remove(archive)
            raise RuntimeError('{} does not match {}; deleted, please run again'.format(name, source))
        check, checked = 'SHA-256 matches ' + source, True
    else:
        check, checked = 'NOT CHECKED: ' + source, None
    say('  {}: {}'.format(name, check))
    unpack(archive, folder)
    app = findApp(folder)
    if not app:
        raise RuntimeError('no subsync-cmd in ' + name)
    return app, '{}, {}'.format(tag, check), checked


# --- end-to-end tests -------------------------------------------------------

def appTemp(app, data):
    """A temporary folder of the app's own, where it keeps its transcripts and
    translations. Each version of SubSync Echo expects transcripts made its own
    way, and the cache doesn't tell versions apart: an app reusing another
    one's transcript can refuse a right result. A second run of the same app
    still reuses its own."""
    key = hashlib.sha1(os.path.abspath(app).lower().encode('utf-8')).hexdigest()[:10]
    folder = os.path.join(data, 'temp', key)
    os.makedirs(folder, exist_ok=True)
    return folder


def runFilm(key, app, data, temp):
    name, script, sub = FILMS[key]
    heading(name)
    env = dict(os.environ, TEMP=temp, TMP=temp, TMPDIR=temp)
    start = time.time()
    code = subprocess.call([sys.executable, os.path.join(ROOT, script), '--app', app,
                            '--data', os.path.join(data, sub),
                            '--work', os.path.join(data, 'work', sub), '--download'], env=env)
    return code == 0, minutes(time.time() - start)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0],
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog='\n\n'.join(__doc__.split('\n\n')[1:]))
    parser.add_argument('what', nargs='?', default='unit', choices=['unit', 'e2e', 'all'])
    parser.add_argument('--app')
    parser.add_argument('--release')
    parser.add_argument('--films', default='tos,sita')
    parser.add_argument('--data', default='e2e-data')
    parser.add_argument('--install', action='store_true')
    parser.add_argument('-v', dest='verbose', action='store_true')
    args = parser.parse_args()

    films = [f.strip() for f in args.films.split(',') if f.strip()]
    for f in films:
        if f not in FILMS:
            parser.error('unknown film {!r}, choose from {}'.format(f, ', '.join(FILMS)))

    say('SubSync Echo tests: Python {}, {} {}'.format(platform.python_version(),
        platform.system(), platform.machine()))
    results = []        # (part, passed, detail)

    if args.install and not install():
        results.append(('installing packages', False, 'pip failed'))

    if args.what in ('unit', 'all'):
        start = time.time()
        ok, detail = runUnit(args.verbose)
        results.append(('unit tests', ok, '{}, {}'.format(detail, minutes(time.time() - start))))

    if args.what in ('e2e', 'all'):
        data = os.path.abspath(args.data)
        os.makedirs(data, exist_ok=True)
        app = args.app
        if app and os.path.exists(app):
            app = os.path.abspath(app)
        if not app:
            heading('SubSync Echo to test')
            try:
                # an unchecked download is reported (NOTE), but isn't a test failure
                app, check, checked = releaseApp(data, args.release)
                results.append(('SubSync Echo release', checked, check))
            except Exception as err:
                say('error: {}'.format(err))
                results.append(('getting the app', False, str(err)))
        if app:
            temp = appTemp(app, data)
            say('\napp: ' + app)
            say('its transcripts and translations: ' + temp)
            for f in films:
                ok, took = runFilm(f, app, data, temp)
                results.append((FILMS[f][0], ok, took))

    heading('Summary')
    for part, ok, detail in results:
        say('  {:<22} {:<5} {}'.format(part, {True: 'PASS', False: 'FAIL', None: 'NOTE'}[ok], detail))
    if not results:
        say('  nothing was run')
    passed = bool(results) and all(ok is not False for _, ok, _ in results)
    say('\n' + ('Everything passed.' if passed else 'Something failed: see the output above.'))
    return 0 if passed else 1


if __name__ == '__main__':
    sys.exit(main())
