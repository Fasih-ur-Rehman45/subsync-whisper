"""Extracting zip archives without writing outside the target folder.

Imports nothing from SubSync, so it is tested on its own.
"""

import os


def unsafeMembers(zipf, dstdir):
    """Names in the archive that would land outside `dstdir`: absolute
    paths, drive letters, '..' (zipfile drops these when extracting, but an
    archive holding them is not one SubSync made)."""
    root = os.path.realpath(dstdir)
    bad = []
    for name in zipf.namelist():
        parts = name.replace('\\', '/').split('/')
        path = os.path.realpath(os.path.join(root, *parts))
        if (os.path.isabs(name) or name.startswith(('/', '\\')) or ':' in parts[0]
                or '..' in parts or os.path.commonpath([ root, path ]) != root):
            bad.append(name)
    return bad


def extractAll(zipf, dstdir):
    """Extract every member to `dstdir`, refusing the whole archive when any
    member would land outside it (raises ValueError, nothing is written)."""
    bad = unsafeMembers(zipf, dstdir)
    if bad:
        raise ValueError('archive member outside the target folder: %s' % ', '.join(bad[:5]))
    zipf.extractall(dstdir)
