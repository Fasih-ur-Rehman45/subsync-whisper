# Changelog

All notable changes to SubSync Echo are listed here, newest first. Version numbers continue from the original SubSync (last release 0.17).

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Add every change under **Unreleased**. When releasing, rename that section to the new version and date. The release page takes its "What's new" from that section.

## [Unreleased]

### Fixed
- **English films with English subtitles** (and other languages the original SubSync method handles) could come out up to half a second off near the end of a long film, depending on the computer: the original method stops listening once its answer looks good enough, and how much of the film it has heard by then depends on the processor. Its result is now checked against the speech detected in the whole film, polished (speed, offset, and the start-of-speech timing used for other films) and kept as found when speech doesn't confirm it. No download is needed; it adds about 30 seconds per film on the test laptop. On 11 English films, mistimed: 7 with all lines within 0.2 s (Cars was 65% before), 4 consistently timed differently by their files; on Sita Sings the Blues, the English result no longer depends on the computer (100% in every simulated early stop).

- **A song could block a sync.** Whisper's speech filter cuts out music and sometimes joins the speech on both sides of a song into one transcript line, which then lasts far longer than its words (75 seconds for a line said in 4) and is timed up to a minute early. A few such lines made a transcribed part of Sita Sings the Blues "disagree" with the right timing, and Spanish subtitles were refused on Linux. Transcript lines lasting more than 3 times their reading time plus 10 seconds are now left out, also from transcripts made before; in short videos, parts left with fewer than 10 lines are judged together with others instead of being skipped, and like any part with too few matches they can confirm a timing but not block it. The 26 test cases on 9 Japanese films, Tears of Steel and Sita Sings the Blues give the same results as before.

- **Long sentences split by Whisper could block a sync.** Each transcribed part is checked by matching its lines with the subtitles. A match counted as on time only when the transcript line started within 2 seconds of its subtitle line's start, but Whisper sometimes splits one long subtitle sentence into pieces, and the later pieces start 2–3 seconds in, while the line is still shown. In fast dialogue of Sita Sings the Blues, these made a part "disagree" with the right timing, and Spanish subtitles were refused in one Linux run (whether Whisper splits a sentence can differ between computers). A transcript line starting while its subtitle line is shown now counts as on time; subtitles of a different cut are still caught, as they are off by far more than a line lasts. With the same Linux transcripts, Spanish now syncs with all lines within 0.2 s; the 26 test cases on 9 Japanese films, Tears of Steel and the other Sita languages give the same results as before.

- A download of one speech model could stand in for another's: while one Whisper model was downloading, a request for a different model waited for it and then went on as if its own model were there. Downloads are now kept per model. The translation model's download can no longer be started twice by two callers at once.

### Security
- Downloaded asset archives (the original method's speech models and dictionaries) are refused as a whole when any file in them would be written outside the asset folder. These archives were already signature-checked, and Python's zip extraction already drops `..` from paths; this is a second safeguard.
- `SECURITY.md` says how to report a security problem privately, which versions get fixes, and how each download is checked.
- Release pages list a `SHA256SUMS` file with the checksum of every download.

### Changed
- **The project is now called SubSync Echo** (README, release pages), to tell it apart from the original SubSync. Its README and release pages now open with what it does for every language, not only Japanese. The app and its files keep the name `subsync`, and the repository moved and was renamed to [Z0rdic/SubSync-Echo](https://github.com/Z0rdic/SubSync-Echo) (links to the old addresses, including subsync-whisper, redirect).
- **The README is written for everyday users first:** what it does, the before/after clip, a 3-step quick start, "Is this for me?" (what it fixes and what it can't do), installing, using it, a short summary of the test results, and answers to common questions (privacy, files and languages it works with, what to try when it can't sync, where it keeps its files). The full test tables, the language table and how it works moved to [doc/results.md](doc/results.md); building, testing and releasing to [doc/development.md](doc/development.md).
- **Builds use exact package versions.** The release builds installed the newest wxPython, PyInstaller, NumPy, ONNX Runtime, PyAV, CTranslate2 and their dependencies at build time, so a new release of any of them could change a download without any change here. `.github/constraints.txt` now pins all 43 packages to the versions of the last tested build (Windows and Linux resolve to exactly these versions; wxPython is 4.3.2 on Windows and 4.2.5 on Linux, the newest ready-made one for Ubuntu 22.04). The app itself is unchanged.

### Added
- **The README shows what it does:** a silent before/after clip from Tears of Steel, with the audio and the speech SubSync detects drawn under the film, so you can see the mistimed lines appear over silence and the synced ones over speech (the synced file is the app's own output in its end-to-end test). Also screenshots of the window, from a first run with Spanish subtitles on that film (44 seconds), and badges for the build, the latest release, the license and the platforms.
- **How the accuracy tests are done:** `doc/benchmark.md` describes the answer keys, the timing errors applied, how lines are scored, the timing-style rule, which test sets anyone can rerun and the machines used.
- **End-to-end test on a full-length film with many songs.** `tests/e2e/sita_sings_the_blues.py` syncs subtitles of Sita Sings the Blues (Nina Paley, public domain, 82 minutes, about a third of its lines sung) in English, Spanish, Chinese, Czech and French, mistimed by a 4.3% speed difference plus 9.4 s, and scores song lines and dialogue separately. English, Spanish, Chinese and Czech: all lines within 0.2 s, songs as well as dialogue; the French file is timed about 0.3 s later than SubSync's target throughout, so it is shown but doesn't fail the test. It runs on both packages before every release, like the Tears of Steel test.

## [0.20] - 2026-11-15

### Fixed
- **Japanese subtitles with Japanese audio** (and Chinese) could never be confirmed: the check of transcribed parts compared whole phrases, because these languages are written without spaces. It now compares short groups of letters, like the original SubSync's matching does. On a 97-minute Japanese film with correctly timed Japanese subtitles, SubSync confirmed them after 2 of 20 parts and kept every line within 0.08 s.
- **Short videos** (TV episodes, short films) with subtitles made for another frame rate, for example 25 fps subtitles on a 23.976 fps video, often failed or came out a little off: a few minutes of speech pin the speed down less precisely than a whole film. In videos under 30 minutes, the speed is now searched more widely and set exactly to the frame rate conversion, and the video is split into at least 4 parts, judged together when each has too few words. Tested with the official subtitles of Tears of Steel (12 minutes) in Spanish, German, Italian, Dutch and Russian: all lines within 0.2 s of the official timing, where before 3 of 5 failed. Films keep their previous behaviour; the 26 test cases on 9 Japanese films give the same results.
- **Chosen audio channels are used by Whisper too.** Like the original method, it now listens by default only to the center channel of 5.1 audio, where the dialogue is, instead of all channels mixed with the music and effects, and follows the channels chosen in the settings or with `--ref-channels`.

### Changed
- **Timing matches the film's subtitle tradition.** Lines start 0.25 s before speech for films in other languages and 0.15 s for English-language films, the typical values measured on 26 subtitle files (9 Japanese films, 13 English films, 4 in other languages). Before, 0.25 s was used for every film.
- **About 20% faster.** Whisper no longer works out the timing of every word, which SubSync never used. Measured on 3 films in both orders: 117 s instead of 146 s on average, with the same accuracy.
- The speech model is loaded once and reused, so language detection and several files in batch mode don't load it again each time (it took about 7 s per load).
- The README says plainly which stretches of a film are checked, and how each combination of subtitle and audio language is handled.
- The About window credits the translation model (M2M100) and SentencePiece.
- Building from source: the declared versions match what is tested. pysubs2 is limited to versions below 2, Python 3.6 is the oldest supported (Whisper and translation need 3.9; releases use 3.12), and `pip install '.[whisper]'` installs translation too.
- The speech and translation models are downloaded at the exact versions they were tested with, so a change in their Hugging Face repositories (the translation model's belongs to a third party) can't change results unnoticed. Models already downloaded stay valid.
- The macOS packaging files were removed: they predate Whisper and were never built or tested by this version.

### Added
- **Linux version.** A portable folder for 64-bit Linux (Ubuntu 22.04 or newer, Debian 12, Fedora 36 and similar): unpack the `.tar.xz` and run `./subsync/subsync`, nothing to install.
- **Any combination of subtitle and audio languages.** Whisper can only translate speech to English, so subtitles in other languages are now translated to English on your computer, just for matching; your subtitles are never changed. This also covers the reverse direction, English films with subtitles in another language. It needs a one-time download of a translation model (about 490 MB, MIT license), and SubSync asks first. Tested with Spanish and Polish subtitles on 3 Japanese films (all 100% within 0.2 s), and with real Portuguese and Bulgarian subtitles on an English film (100%).
- **Whisper fallback for English films with English subtitles.** These still go through the original SubSync method first; when it can't sync them, Whisper now writes down the English speech and matches it with the subtitles, instead of no file being saved. The command line downloads the speech model for it the first time (unless run with `--offline`); the app window uses it when the model is already downloaded. Tears of Steel's English subtitles: the original method saved nothing, the fallback got all lines within 0.2 s.
- **End-to-end test on a free film.** `tests/e2e/tears_of_steel.py` syncs the official subtitles of Tears of Steel (Blender Foundation, CC-BY) in 6 languages with the built app and scores every line against the official timing (lines are paired by their text, a missing line counts as wrong); anyone can rerun it. All 6 languages: all lines within 0.2 s. It runs on both the Windows and the Linux package before every release, which is published only when it passes.
- Unit tests for the timing logic (speech polish, per-part and region checks, piece-by-piece sync, the start-of-speech correction), on synthetic films with known right answers. They run on every build, and also check that faster-whisper still has the parts of it SubSync relies on.

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

[Unreleased]: https://github.com/Z0rdic/SubSync-Echo/compare/0.20...HEAD
[0.20]: https://github.com/Z0rdic/SubSync-Echo/releases/tag/0.20
[0.19]: https://github.com/Z0rdic/SubSync-Echo/releases/tag/0.19
[0.18]: https://github.com/Z0rdic/SubSync-Echo/releases/tag/0.18
[0.17]: https://github.com/sc0ty/subsync/releases/tag/0.17
