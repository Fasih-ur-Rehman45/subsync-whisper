# Building, testing and releasing

[Back to the README](../README.md)

Windows and Linux packages are built by GitHub Actions; see [.github/workflows/build.yml](../.github/workflows/build.yml) for every step. The exact version of every Python package the builds install is in [.github/constraints.txt](../.github/constraints.txt).

The timing logic has unit tests on synthetic films with known right answers. They run on every build, or locally in a few seconds (needs Python with numpy):

```
python -m unittest discover -s tests -v
```

The end-to-end test syncs the official subtitles of Tears of Steel with the built app and scores every line against the official timing. It runs on both packages before every release, and a release is published only when it passes. `--download` fetches the film (372 MB) and its subtitles from blender.org first:

```
python tests/e2e/tears_of_steel.py --app dist/subsync/subsync-cmd.exe --data tos --download
```

A second end-to-end test does the same on Sita Sings the Blues, a full-length film with many songs, and scores song lines and dialogue separately. It runs before every release too. `--download` fetches the film (481 MB) from archive.org and its subtitles from Amara and archive.org:

```
python tests/e2e/sita_sings_the_blues.py --app dist/subsync/subsync-cmd.exe --data sita --download
```

To release a version:
1. In [CHANGELOG.md](../CHANGELOG.md), rename **Unreleased** to the new version and date.
2. Push a version tag such as `0.21`.

The tag builds the package and publishes a release. Its "What's new" comes from that changelog section. A tag without a changelog entry stops before building.

## The icon

The app's icon is drawn in two SVG files: [resources/subsync.svg](../resources/subsync.svg), the full design, used from 64 px, and [resources/subsync-small.svg](../resources/subsync-small.svg), a bolder version for 16–48 px, where fine lines blur. The Windows `.ico`, the macOS `.icns` and the app's PNG images (`subsync/img/icon.png` from the small drawing, `logo.png` from the full one) are made from them.
