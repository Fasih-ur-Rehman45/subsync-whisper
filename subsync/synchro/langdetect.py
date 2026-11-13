"""Detection of the reference audio language, when the file doesn't say it.

Most video files don't store the language of their audio. Whisper (see
`subsync.synchro.transcribe.getLanguage`) recognizes it from a few minutes of
speech, so the user doesn't have to know which language to select.
"""

from subsync.synchro import transcribe
from subsync.data import languages

import logging
logger = logging.getLogger(__name__)


def needsDetection(task):
    """Check whether reference audio of `task` has no language and it can be
    detected (faster-whisper is installed)."""
    ref = task.ref
    return bool(ref and ref.path and ref.type == 'audio' and not ref.lang
            and transcribe.isAvailable())


def detect(task, runCb=None):
    """Detect spoken language of task's reference audio and set it.

    Returns
    -------
    tuple of (str, float) or None
        3-letter language code and its probability, `None` when not detected.
    """
    res = transcribe.getLanguage(task.ref.path, task.ref.no, runCb=runCb)
    if not res:
        logger.info('audio language of %s not detected', task.ref.path)
        return None

    code3 = languages.get(code2=res[0]).code3
    if not code3:
        logger.info('detected audio language %s is not supported', res[0])
        return None

    logger.info('audio language of %s detected: %s (%.0f%%)',
            task.ref.path, code3, 100 * res[1])
    task.ref.lang = code3
    return code3, res[1]
