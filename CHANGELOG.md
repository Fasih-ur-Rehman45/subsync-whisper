# Changelog

All notable changes to this version of SubSync are listed here, newest first. Version numbers continue from the original SubSync (last release 0.17).

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Add every change under **Unreleased**. When releasing, rename that section to the new version and date. The release page takes its "What's new" from that section.

## [Unreleased]

### Fixed
- **Japanese subtitles with Japanese audio** (and Chinese) could never be confirmed: the check of transcribed parts compared whole phrases, because these languages are written without spaces. It now compares short groups of letters, like the original SubSync's matching does.

### Changed
- **Timing matches the film's subtitle tradition.** Lines start 0.25 s before speech for films in other languages and 0.15 s for English-language films, the typical values measured on 26 subtitle files (9 Japanese films, 13 English films, 4 in other languages). Before, 0.25 s was used for every film.
- **About 20% faster.** Whisper no longer works out the timing of every word, which SubSync never used. Measured on 3 films in both orders: 117 s instead of 146 s on average, with the same accuracy.
- The speech model is loaded once and reused, so language detection and several files in batch mode don't load it again each time (it took about 7 s per load).
- The README says plainly which stretches of a film are checked, and how each combination of subtitle and audio language is handled.
- The About window credits the translation model (M2M100) and SentencePiece.

### Added
- **Linux version.** A portable folder for 64-bit Linux (Ubuntu 22.04 or newer, Debian 12, Fedora 36 and similar): unpack the `.tar.xz` and run `./subsync/subsync`, nothing to install.
- **Any combination of subtitle and audio languages.** Whisper can only translate speech to English, so subtitles in other languages are now translated to English on your computer, just for matching; your subtitles are never changed. This also covers the reverse direction, English films with subtitles in another language. It needs a one-time download of a translation model (about 490 MB, MIT license), and SubSync asks first. Tested with Spanish and Polish subtitles on 3 Japanese films (all 100% within 0.2 s), and with real Portuguese and Bulgarian subtitles on an English film (100%).
- Unit tests for the timing logic (speech polish, per-part and region checks, piece-by-piece sync, the start-of-speech correction), on synthetic films with known right answers. They run on every build.

## [0.19] - 2026-11-14

### Added
- **More accurate timing.** Lines now start a moment before people speak, the way subtitles are written, instead of sitting over the speech a little late. The lead is a typical value (a quarter second) measured on the test films' correct subtitles. On 8 of the 9 test films, lines are now on average 0.04 s from the correct timing instead of 0.12 s.
- **The audio language is detected automatically.** Most video files don't say which language their audio is in, so it no longer has to be selected by hand: when it's not set, SubSync listens to a few minutes of speech and selects it, in about 10 seconds. This works in the app, in batch mode and on the command line.
- **Portable `.exe`**, like the original SubSync's: run it, choose where to unpack, and it creates a `subsync` folder with the app. The zip is still available.

### Changed
- The README now describes this version: install, use, results, troubleshooting and credits.
- The About window's Website button opens this project's page. Its credits now include the speech recognition components, and FFmpeg's license is corrected to GPL-3.0 with a link to its source code.
- Release pages are now a short overview (what's new and how to get started) that links to the README for the full guide.
- A bug report form on GitHub asks for the details needed to fix a problem, including the log. The README explains how to save the log.
- This changelog was added. Release pages take their "What's new" from it, and a release can't be published without an entry.

### Fixed
- "Please wait" windows (detecting the audio language, downloading the list of speech models for other languages) failed with the current wxPython and are shown again.

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

[Unreleased]: https://github.com/Fasih-ur-Rehman45/subsync-whisper/compare/0.19...HEAD
[0.19]: https://github.com/Fasih-ur-Rehman45/subsync-whisper/releases/tag/0.19
[0.18]: https://github.com/Fasih-ur-Rehman45/subsync-whisper/releases/tag/0.18
[0.17]: https://github.com/sc0ty/subsync/releases/tag/0.17
