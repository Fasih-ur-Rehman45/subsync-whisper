"""Write the release page text for a version.

Takes that version's section of CHANGELOG.md and puts it into the
.github/release-notes.md template. Fails when the changelog has no entry for
the version, so a release can't be published without one.

usage: python .github/release_notes.py VERSION [OUTPUT]
"""

import os
import re
import sys

root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def changes(version):
    with open(os.path.join(root, 'CHANGELOG.md'), encoding='utf-8') as fp:
        text = fp.read()
    # section from "## [version]" to the next "## [" heading or link list
    match = re.search(r'^## \[' + re.escape(version) + r'\][^\n]*\n(.*?)(?=^## \[|^\[[^\]]+\]: |\Z)',
            text, re.MULTILINE | re.DOTALL)
    return match.group(1).strip() if match else ''


def main(argv):
    if len(argv) < 2:
        print(__doc__.strip(), file=sys.stderr)
        return 2

    version = argv[1]
    section = changes(version)
    if not section:
        print('CHANGELOG.md has no entry for {}: rename "Unreleased" to "{}" '
                'with the date before tagging'.format(version, version), file=sys.stderr)
        return 1

    with open(os.path.join(root, '.github', 'release-notes.md'), encoding='utf-8') as fp:
        template = fp.read()
    template = re.sub(r'\A<!--.*?-->\s*', '', template, flags=re.DOTALL)
    body = template.replace('{{CHANGES}}', section).replace('{{VERSION}}', version)

    if len(argv) > 2:
        with open(argv[2], 'w', encoding='utf-8', newline='\n') as fp:
            fp.write(body)
    else:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stdout.write(body)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
