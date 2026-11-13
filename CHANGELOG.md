# Changelog

All notable changes to this version of SubSync are listed here, newest first. Version numbers continue from the original SubSync (last release 0.17).

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Add every change under **Unreleased**. When releasing, rename that section to the new version and date. The release page takes its "What's new" from that section.

## [Unreleased]

### Added
- **Portable `.exe`**, like the original SubSync's: run it, choose where to unpack, and it creates a `subsync` folder with the app. The zip is still available.

### Changed
- The README now describes this version: install, use, results, troubleshooting and credits.
- The About window's Website button opens this project's page. Its credits now include the speech recognition components, and FFmpeg's license is corrected to GPL-3.0 with a link to its source code.
- Release pages are now a short overview (what's new and how to get started) that links to the README for the full guide.
- A bug report form on GitHub asks for the details needed to fix a problem, including the log. The README explains how to save the log.
- This changelog was added. Release pages take their "What's new" from it, and a release can't be published without an entry.

## [0.18] - 2026-11-13

### Added
- **Japanese audio support.** English subtitles can now be synchronized to Japanese films. Speech is recognized with the Whisper speech recognition model and translated to English on your computer.
- **34 more languages** without a SubSync speech model are handled the same way (untested so far).
- **Fast syncing.** Only a few parts of the film are transcribed, and syncing stops once the timing is confirmed: about 2–3 minutes per film without a graphics card.
- **Wrong results are refused.** The timing is saved only when the detected speech and every part of the film agree with it.
- **Subtitles from a different cut** (scenes added or removed) are synchronized piece by piece.
- **One-time model download.** The first sync asks before downloading the speech model (about 490 MB) and shows its progress, in the app and on the command line. A failed download gives a clear "check your internet connection" message.
- Transcripts are kept, so syncing the same film again is quick.

### Changed
- Built for current Windows with Python 3.12, with everything included in one folder.
- Automatic updates are turned off, because the original update server would replace this version with one that has no Japanese support.

### Fixed
- Sliders and progress bars work with the current wxPython.

## [0.17] - 2021-11-11

Last release of the original [SubSync](https://github.com/sc0ty/subsync/releases/tag/0.17) by Michał Szymaniak.

[Unreleased]: https://github.com/Fasih-ur-Rehman45/subsync-whisper/compare/0.18...HEAD
[0.18]: https://github.com/Fasih-ur-Rehman45/subsync-whisper/releases/tag/0.18
[0.17]: https://github.com/sc0ty/subsync/releases/tag/0.17
