"""Machine translation of subtitle lines to English, for matching only.

Whisper can translate speech only to English. To synchronize subtitles in any
other language, they are translated to English too, and the two English texts
are matched (the subtitles themselves are never changed). Translation runs on
this computer with the M2M100 model (MIT license, 100 languages) on the same
engine as Whisper (CTranslate2), and is cached like transcripts are.

Like transcribe.py, this module imports nothing from subsync, so it can run in
a separate Python (see `findPython`):

    python subsync/synchro/translate.py --src es --in lines.json --out english.json
"""

import hashlib
import json
import os
import re
import sys
import tempfile
import threading

import logging
logger = logging.getLogger(__name__)


# int8 conversion of facebook/m2m100_418M for CTranslate2, MIT license
modelRepo = 'jncraton/m2m100_418M-ct2-int8'
modelFiles = [ 'model.bin', 'config.json', 'sentencepiece.bpe.model',
        'shared_vocabulary.json', 'generation_config.json', 'README.md' ]
modelSize = 491e6
cacheVersion = 1

# languages of the model (2-letter codes, a few longer ones)
languages = set('''af am ar ast az ba be bg bn br bs ca ceb cs cy da de el en es
        et fa ff fi fr fy ga gd gl gu ha he hi hr ht hu hy id ig ilo is it ja jv ka
        kk km kn ko lb lg ln lo lt lv mg mk ml mn mr ms my ne nl no ns oc or pa pl ps
        pt ro ru sd si sk sl so sq sr ss su sv sw ta th tl tn tr uk ur uz vi wo xh yi
        yo zh zu'''.split())

# lines are translated in groups, the progress is reported between them
groupSize = 128
# translation is limited by memory speed, more threads don't make it faster
threads = 4


class Terminated(Exception):
    """Translation was cancelled by the caller."""


class NotInstalled(Exception):
    def __init__(self):
        super().__init__('translation is not installed, install it with: '
                'pip install ctranslate2 sentencepiece huggingface_hub')


class DownloadFailed(Exception):
    """Model could not be downloaded, usually there is no internet."""


def supports(lang):
    """Check whether subtitles in this language (2-letter code) can be
    translated to English."""
    return bool(lang) and lang.lower() in languages and lang.lower() != 'en'


importError = None


def _hasModules():
    global importError
    try:
        import ctranslate2, sentencepiece, huggingface_hub  # noqa: F401
        return True
    except ImportError as err:
        importError = repr(err)
        return False


def availability():
    """How translation can be used here, for --version and bug reports."""
    if _hasModules():
        return 'available'
    python = findPython()
    if python:
        return 'available through {}'.format(python)
    return 'not available ({})'.format(importError)


def findPython():
    """Python with the translation modules, when SubSync's own doesn't have
    them: SUBSYNC_WHISPER_PYTHON or `.whisper` next to the sources."""
    path = os.environ.get('SUBSYNC_WHISPER_PYTHON')
    if path:
        return path if os.path.isfile(path) else None
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    for sub in (('Scripts', 'python.exe'), ('bin', 'python')):
        path = os.path.join(root, '.whisper', *sub)
        if os.path.isfile(path):
            return path


def isAvailable():
    return _hasModules() or bool(findPython())


# --- model ------------------------------------------------------------------

def _modelPath(localOnly):
    from huggingface_hub import snapshot_download
    return snapshot_download(modelRepo, allow_patterns=modelFiles, local_files_only=localOnly)


def isModelInstalled():
    """`True` or `False`, `None` when translation runs in separate Python
    (it then downloads the model itself)."""
    if not _hasModules():
        return None
    try:
        _modelPath(localOnly=True)
        return True
    except Exception:
        return False


def _downloadedBytes():
    try:
        from huggingface_hub.constants import HF_HUB_CACHE
        folder = os.path.join(HF_HUB_CACHE, 'models--' + modelRepo.replace('/', '--'))
        return sum(os.path.getsize(os.path.join(root, name))
                for root, dirs, files in os.walk(folder) for name in files)
    except Exception:
        return 0


_download = None


def downloadModel(runCb=None, progressCb=None):
    """Download the model unless already there, see transcribe.downloadModel.

    Returns `False` when stopped by `runCb`; raises `DownloadFailed`.
    """
    global _download
    if isModelInstalled() is not False:
        return True

    if _download is None or not _download['thread'].is_alive():
        state = { 'error': None }

        def run():
            try:
                logger.info('downloading translation model %s', modelRepo)
                _modelPath(localOnly=False)
            except Exception as err:
                logger.warning('translation model download failed: %r', err, exc_info=True)
                state['error'] = err

        state['thread'] = threading.Thread(target=run, name='TranslationDownload', daemon=True)
        state['thread'].start()
        _download = state

    state = _download
    while state['thread'].is_alive():
        if progressCb:
            progressCb(_downloadedBytes(), modelSize)
        if runCb and not runCb():
            return False
        state['thread'].join(timeout=0.25)

    if state['error'] is not None:
        raise DownloadFailed('could not download translation model, '
                'check internet connection ({})'.format(state['error']))
    return True


_loaded = None
_loadedLock = threading.Lock()


def loadModel():
    """Translator and tokenizer, loaded once."""
    global _loaded
    try:
        import ctranslate2
        import sentencepiece
    except ImportError:
        raise NotInstalled()

    with _loadedLock:
        if _loaded is None:
            try:
                path = _modelPath(localOnly=True)
            except Exception:
                if isModelInstalled() is False:
                    raise DownloadFailed('translation model is not downloaded')
                raise
            logger.info('loading translation model %s', path)
            tokenizer = sentencepiece.SentencePieceProcessor(
                    model_file=os.path.join(path, 'sentencepiece.bpe.model'))
            translator = ctranslate2.Translator(path, device='cpu',
                    compute_type='int8', intra_threads=threads)
            _loaded = (translator, tokenizer)
        return _loaded


# --- translation ------------------------------------------------------------

def cleanText(text):
    """Plain text of a subtitle line: formatting tags and line breaks removed."""
    text = re.sub(r'\{[^}]*\}|<[^>]*>|\\[Nnh]', ' ', text)
    return ' '.join(text.split())


def translateLines(texts, src, tgt='en', runCb=None, progressCb=None):
    """Translate lines in this process.

    Parameters
    ----------
    texts: list of str
    src, tgt: str
        2-letter language codes.
    progressCb: callable, optional
        Called with (lines done, lines total).

    Returns
    -------
    list of str
        Translations, one for every line (empty lines stay empty).
    """
    translator, tokenizer = loadModel()
    out = [ '' ] * len(texts)
    todo = [ (no, cleanText(text)) for no, text in enumerate(texts) ]
    todo = [ (no, text) for no, text in todo if text ]

    for first in range(0, len(todo), groupSize):
        if runCb and not runCb():
            raise Terminated()
        group = todo[first:first + groupSize]
        source = [ [ '__{}__'.format(src) ] + tokenizer.encode(text, out_type=str) + [ '</s>' ]
                for _, text in group ]
        res = translator.translate_batch(source,
                target_prefix=[ [ '__{}__'.format(tgt) ] ] * len(group),
                beam_size=1, max_decoding_length=96,
                max_batch_size=2048, batch_type='tokens')
        for (no, _), r in zip(group, res):
            out[no] = tokenizer.decode(r.hypotheses[0][1:])
        if progressCb:
            progressCb(min(first + groupSize, len(todo)), len(todo))
    return out


def getCachePath(texts, src, tgt='en'):
    key = json.dumps([ modelRepo, cacheVersion, src, tgt, texts ], ensure_ascii=False)
    name = hashlib.sha1(key.encode('utf-8')).hexdigest()[:20] + '.json'
    return os.path.join(tempfile.gettempdir(), 'subsync-translations', name)


def getTranslation(texts, src, tgt='en', runCb=None, progressCb=None):
    """Translate lines, in this process or in separate Python, cached."""
    path = getCachePath(texts, src, tgt)
    try:
        with open(path, encoding='utf-8') as fp:
            res = json.load(fp)
        if isinstance(res, list) and len(res) == len(texts):
            logger.info('translation from cache %s', path)
            return res
    except (OSError, ValueError):
        pass

    if _hasModules():
        res = translateLines(texts, src, tgt, runCb, progressCb)
    else:
        python = findPython()
        if not python:
            raise NotInstalled()
        res = _translateExternal(python, texts, src, tgt, runCb, progressCb)

    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + '.part'
    with open(tmp, 'w', encoding='utf-8') as fp:
        json.dump(res, fp, ensure_ascii=False)
    os.replace(tmp, path)
    return res


def _translateExternal(python, texts, src, tgt, runCb=None, progressCb=None):
    import subprocess

    folder = tempfile.mkdtemp(prefix='subsync-translate-')
    inPath, outPath = os.path.join(folder, 'in.json'), os.path.join(folder, 'out.json')
    try:
        with open(inPath, 'w', encoding='utf-8') as fp:
            json.dump(texts, fp, ensure_ascii=False)
        cmd = [ python, os.path.abspath(__file__), '--src', src, '--tgt', tgt,
                '--in', inPath, '--out', outPath, '--machine' ]
        logger.info('running translation: %s', ' '.join(cmd))
        flags = 0x08000000 if sys.platform == 'win32' else 0  # no console window
        env = dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONUTF8='1')
        proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE, creationflags=flags, env=env)
        errors = []

        def reader():
            for raw in proc.stderr:
                line = raw.decode('utf-8', 'replace').strip()
                if line.startswith('progress ') and progressCb:
                    progressCb(*map(int, line.split()[1:3]))
                elif line:
                    errors.append(line)

        thread = threading.Thread(target=reader, daemon=True)
        thread.start()
        while thread.is_alive():
            thread.join(timeout=0.5)
            if runCb and not runCb():
                proc.kill()
                raise Terminated()
        if proc.wait() != 0:
            raise RuntimeError('translation failed: {}'.format(' '.join(errors[-3:])))
        with open(outPath, encoding='utf-8') as fp:
            return json.load(fp)
    finally:
        for p in (inPath, outPath):
            if os.path.exists(p):
                os.remove(p)
        os.rmdir(folder)


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description='Translate subtitle lines (JSON list of strings).')
    parser.add_argument('--src', required=True, help='source language, 2-letter code')
    parser.add_argument('--tgt', default='en', help='target language (default: en)')
    parser.add_argument('--in', dest='inPath', required=True)
    parser.add_argument('--out', dest='outPath', required=True)
    parser.add_argument('--machine', action='store_true', help='machine readable progress')
    args = parser.parse_args(argv)

    with open(args.inPath, encoding='utf-8') as fp:
        texts = json.load(fp)

    def progress(done, total):
        if args.machine:
            sys.stderr.write('progress {} {}\n'.format(done, total))
            sys.stderr.flush()

    res = translateLines(texts, args.src, args.tgt, progressCb=progress)
    with open(args.outPath, 'w', encoding='utf-8') as fp:
        json.dump(res, fp, ensure_ascii=False)
    return 0


if __name__ == '__main__':
    sys.exit(main())
