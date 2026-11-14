# SubSync with Japanese audio support

SubSync fixes subtitles that are out of sync with a video. It listens to the video's audio and moves the subtitles to where the lines are actually spoken.

This version adds **Japanese audio**. The original SubSync has no speech model for Japanese, so anime and other Japanese films couldn't be synchronized. Here, Japanese speech is recognized with the Whisper speech recognition model and translated to English, so **English subtitles can be synchronized to Japanese films**. Everything runs on your own computer, without a graphics card.

**[⬇ Download the latest version](https://github.com/Fasih-ur-Rehman45/subsync-whisper/releases/latest)** · [What's changed](CHANGELOG.md)

---

## Requirements

- 64-bit Windows 10 or 11.
- 8 GB of RAM. It uses about 1.5 GB while syncing.
- About 1 GB of disk space: 400 MB for the app and 490 MB for the speech model.
- Internet the first time you sync Japanese audio, to download the speech model.

## Installing

1. Download **`subsync-<version>-portable-amd64.exe`** from **[Releases](https://github.com/Fasih-ur-Rehman45/subsync-whisper/releases/latest)**.
2. Run it and choose where to unpack, for example `Downloads`. It creates a `subsync` folder.
3. Open that folder and run **`subsync.exe`**.

The same app is also available as a zip (`subsync-<version>-windows-x64.zip`). Unzip it anywhere and run `subsync.exe`.

Windows may show *"Windows protected your PC"* the first time, because SubSync is new and not yet known to Windows. Click **More info**, then **Run anyway**.

## Using it

1. **Subtitles:** choose your subtitle file and set its language to **English**.
2. **References:** choose the video file. If its language box stays empty, leave it: SubSync detects the spoken language when you click Start (about 10 seconds).
3. Click **Start**. The first time only, agree to download the speech model (about 490 MB).
4. When it says **Subtitles synchronized**, click **Save**.

To sync several files at once, open the menu (**⋮**) and choose **Batch processing**.

Syncing the same film again is quick, because the transcript is kept in `%TEMP%\subsync-transcripts`. That folder can be deleted at any time.

## Reading the result

| Message | Meaning |
|---|---|
| **Subtitles synchronized** | Done. The timing was confirmed by the transcribed parts, and by the speech in every stretch of the film with enough dialogue to judge. |
| **Couldn't synchronize** | The timing couldn't be confirmed, so no file is saved rather than saving wrong timing. |
| **Subtitles do not fit this video as a whole, they may be made for a different cut or release** | The subtitles are for another version of the film, and piece-by-piece sync couldn't confirm a result either. Try subtitles made for your release. |
| **Couldn't download the speech recognition model, check your internet connection** | The first-time download failed. Connect and click Start again; it resumes where it stopped. |

## What it fixes

- **Delays:** everything is a few seconds early or late.
- **Speed differences:** subtitles made for a different frame rate, which get worse over the film.
- **Different cuts:** subtitles made for a version with scenes added or removed are synchronized piece by piece.

It keeps your subtitle text and layout exactly as they were and only changes the timing.

## Speed and accuracy

The test used nine 2-hour Japanese films, with deliberately mistimed copies of correct English subtitles.

| Result | Films |
|---|---|
| **All lines within 0.2 s** of the correct timing | 7 of 9 |
| 90–100% of lines within 0.2 s (a film with few subtitle lines) | 1 of 9 |
| Lines about 0.6 s early (this subtitle file shows every line after the speech starts) | 1 of 9 |
| Different cut, synced piece by piece: 90–100% of lines within 0.2 s | 6 of 6 |

On the first eight films, lines are on average 0.04 s from the correct timing. A 0.2 s difference isn't noticeable when watching.

**Test hardware:** a laptop with an AMD Ryzen 9 5900HX processor and 8 GB of RAM, using no graphics card.

**Time:**
- Most films: 1.5–3 minutes.
- Films with few subtitle lines: up to 6 minutes.

### How it works

SubSync transcribes only a few 5-minute parts of the film, spread from start to end. It fits the timing to them, then checks that timing against the speech detected in the whole film, stretch by stretch (about 15 minutes each). Stretches with too little dialogue to judge (fewer than 30 subtitle lines) aren't checked on their own. It stops as soon as the result is confirmed. That is why a 2-hour film takes minutes rather than the 15–30 minutes a full transcription would take. See [doc/assets.md](doc/assets.md) for details.

### Which languages work how

| Your subtitles and audio | What SubSync does | Tested |
|---|---|---|
| **English subtitles**, audio in Japanese or another language listed below | Whisper translates the speech to English and matches it with your subtitles | Japanese, 9 films |
| **Subtitles in the same language as the audio**, e.g. Japanese subtitles with Japanese audio | Whisper writes down the speech in that language and matches it with your subtitles | Not yet |
| **Any other combination**, e.g. Spanish subtitles with Japanese audio | Whisper translates the speech to English, and your subtitles are translated to English on your computer, only for matching (they are never changed) | Spanish and Polish on 3 Japanese films |
| **English audio with subtitles in another language**, e.g. Japanese subtitles for an English film | Whisper writes down the English speech, and your subtitles are translated to English for matching | Real Portuguese, Bulgarian and French subtitles on 2 films |
| **English audio with English subtitles**, and other languages the original SubSync supports with subtitles in the same language | The original SubSync method, unchanged | By the original project |

Translation needs a second one-time download (about 490 MB) and adds about a minute per film the first time; the result is kept, so syncing the same subtitles again is quick.

The audio language itself is detected with Whisper when the video doesn't say it. That was tested on 34 films in Japanese and English.

## Your privacy

Speech recognition runs on your computer. Your videos and subtitles are never uploaded. The only downloads are the speech model, from `huggingface.co`, and, for languages other than Japanese, the original SubSync's speech models and dictionaries.

## Known limits

- Lines are timed to start a moment before people speak: 0.25 s for films in other languages and 0.15 s for English-language films, the typical values measured on 26 subtitle files. Some subtitles are timed differently, for example showing each line after the speech starts; the result then differs from them by up to a second. Adjust it in **Settings**, under **Output timing offset**.
- Within a few lines of a cut, some lines may land on the wrong side.
- Only Japanese has been tested so far. These audio languages use the same method but are untested: Albanian, Arabic, Belarusian, Bulgarian, Catalan, Croatian, Czech, Danish, Estonian, Faroese, Finnish, Galician, Hebrew, Hungarian, Icelandic, Indonesian, Korean, Latin, Latvian, Lithuanian, Malagasy, Malay, Maltese, Norwegian, Persian, Polish, Portuguese, Romanian, Serbian, Slovak, Slovenian, Swedish, Turkish, Ukrainian.
- All other languages work as in the original SubSync.
- Automatic updates are turned off. New versions appear on the [Releases](https://github.com/Fasih-ur-Rehman45/subsync-whisper/releases) page.

## Advanced settings

These environment variables change how Whisper runs. Set them before starting SubSync.

| Variable | Default | What it does |
|---|---|---|
| `SUBSYNC_WHISPER_MODEL` | `small` | Whisper model size, or a folder with a converted model |
| `SUBSYNC_WHISPER_DEVICE` | `cpu` | `cuda` uses an NVIDIA graphics card, if NVIDIA's cuBLAS and cuDNN libraries are installed (untested) |
| `SUBSYNC_WHISPER_COMPUTE` | `int8` | Number format used for the model |

Smaller models aren't faster here. `tiny` (75 MB) failed to sync all 4 films it was tested on, and `base` (145 MB) failed 1 of 4 and was slower than `small` on the rest, because SubSync needed more parts of the film before it could confirm the timing.

## Troubleshooting

- **To save a log of what SubSync does:**
  1. Open the SubSync folder, click the address bar, type `cmd` and press Enter.
  2. Run `subsync.exe --loglevel=INFO --logfile=log.txt`.
  3. Repeat the sync. The log is written to `log.txt`.

  On the command line, add the same two options to `subsync-cmd.exe`.
- **To report a problem,** use the [bug report form](https://github.com/Fasih-ur-Rehman45/subsync-whisper/issues/new?template=bug_report.yml) and include the log.

## Command line

```
subsync-cmd.exe --cli sync --sub movie.en.srt --sub-lang=eng --ref movie.mkv --ref-stream-by-type=audio --ref-lang=jpn --out movie.synced.srt
```

Run `subsync-cmd.exe --help` for all options.

## Building from source

Windows packages are built by GitHub Actions; see [.github/workflows/build-windows.yml](.github/workflows/build-windows.yml) for every step.

The timing logic has unit tests on synthetic films with known right answers. They run on every build, or locally in a few seconds (needs Python with numpy):

```
python -m unittest discover -s tests -v
```

To release a version:
1. In [CHANGELOG.md](CHANGELOG.md), rename **Unreleased** to the new version and date.
2. Push a version tag such as `0.19`.

The tag builds the package and publishes a release. Its "What's new" comes from that changelog section. A tag without a changelog entry stops before building.

## License and credits

SubSync is free software under the [GNU General Public License v3](LICENSE).

- Based on [SubSync](https://github.com/sc0ty/subsync) by Michał Szymaniak, GPL-3.0.
- Speech recognition: [faster-whisper](https://github.com/SYSTRAN/faster-whisper) and [CTranslate2](https://github.com/OpenNMT/CTranslate2) (MIT), with OpenAI's [Whisper](https://github.com/openai/whisper) `small` model (MIT), downloaded from [Hugging Face](https://huggingface.co/Systran/faster-whisper-small).
- Speech detection: [Silero VAD](https://github.com/snakers4/silero-vad) (MIT), through [ONNX Runtime](https://github.com/microsoft/onnxruntime) (MIT).
- Speech recognition for other languages: [CMU Sphinx](https://github.com/cmusphinx) (BSD).
- Audio and video: [FFmpeg](https://ffmpeg.org) 5.1.2, the [gyan.dev](https://www.gyan.dev/ffmpeg/builds/) full shared build (GPL-3.0); source code at [ffmpeg.org/releases/ffmpeg-5.1.2.tar.xz](https://ffmpeg.org/releases/ffmpeg-5.1.2.tar.xz). Also [PyAV](https://github.com/PyAV-Org/PyAV) (BSD).
- Window: [wxPython](https://wxpython.org) (wxWindows Library Licence). Subtitles: [pysubs2](https://github.com/tkarabela/pysubs2) (MIT). Engine bindings: [pybind11](https://github.com/pybind/pybind11) (BSD).
