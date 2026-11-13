<!-- Release page template. The release workflow replaces {{VERSION}} with the
     version and {{CHANGES}} with that version's section of CHANGELOG.md. -->
**SubSync can now synchronize subtitles to Japanese audio.**

The original SubSync matches subtitles to speech it recognizes in the film's audio. It has no speech model for Japanese, so anime and other Japanese films couldn't be synchronized. This version recognizes Japanese speech with the Whisper speech recognition model and translates it to English, so English subtitles can be matched to Japanese films. Everything runs on your own computer.

## What's new

{{CHANGES}}

## Install

1. Download **`subsync-{{VERSION}}-windows-x64.zip`** under *Assets* below.
2. Unzip it anywhere, for example to `Downloads\SubSync`.
3. Run **`subsync.exe`**.

Windows may show *"Windows protected your PC"* the first time, because SubSync is new and not yet known to Windows. Click **More info**, then **Run anyway**.

## Sync English subtitles to a Japanese film

1. **Subtitles:** choose your `.srt` file and set its language to **English**.
2. **References:** choose the video file and set its language to **Japanese**.
3. Click **Start**. The first time only, agree to download the speech model.
4. When it says **Subtitles synchronized**, click **Save**.

Syncing the same film again is quick, because the transcript is kept in `%TEMP%\subsync-transcripts`.

**Command line:**

```
subsync-cmd.exe --cli sync --sub movie.en.srt --sub-lang=eng --ref movie.mkv --ref-stream-by-type=audio --ref-lang=jpn --out movie.synced.srt
```

## Tested results

The test used nine 2-hour Japanese films, with deliberately mistimed copies of correct English subtitles: wrong speed plus a delay.

| Result | Films |
|---|---|
| **All lines within 0.2 s** of the correct timing | 7 of 9 |
| Follows the speech, but the subtitle file itself was slightly off (drifting, or late everywhere) | 2 of 9 |
| Different cut, synced piece by piece: 80–99% of lines within 0.2 s | 5 of 5 |

A 0.2 s difference isn't noticeable when watching.

**Test hardware:** a laptop with an AMD Ryzen 9 5900HX processor and 8 GB of RAM, using no graphics card.

**Time:**

- Most films: 1.5–3 minutes.
- Films with few subtitle lines: up to 6 minutes.
- The first sync also downloads the model.

## Requirements

- 64-bit Windows 10 or 11.
- 8 GB of RAM. It uses about 1.5 GB while syncing.
- About 1 GB of disk space: 400 MB for the app and 490 MB for the speech model.
- Internet once, to download the model. After that, everything works offline.

## Privacy

Speech recognition runs on your computer. Your video, audio and subtitles are never uploaded. The only download is the speech model, from Hugging Face.

## Messages you may see

| Message | Meaning |
|---|---|
| *Couldn't download the speech recognition model, check your internet connection* | The first-time download failed. Connect and click Start again; the download resumes where it stopped. |
| *Subtitles do not fit this video as a whole, they may be made for a different cut or release* | The subtitles are for another version of the film, and piece-by-piece sync couldn't confirm a result either. Try subtitles made for your release. |
| *Couldn't synchronize* | The result couldn't be confirmed, so nothing was saved rather than saving wrong timing. |

## Known limits

- Lines are timed to the speech. If a subtitle file was deliberately timed differently, for example showing each line after the speech starts, the result can differ from it by up to half a second.
- Within a few lines of a cut, some lines may land on the wrong side.
- Only Japanese has been tested so far.
- Automatic updates are turned off. New versions appear on this page.

## Other supported audio languages (untested)

Albanian, Arabic, Belarusian, Bulgarian, Catalan, Croatian, Czech, Danish, Estonian, Faroese, Finnish, Galician, Hebrew, Hungarian, Icelandic, Indonesian, Korean, Latin, Latvian, Lithuanian, Malagasy, Malay, Maltese, Norwegian, Persian, Polish, Portuguese, Romanian, Serbian, Slovak, Slovenian, Swedish, Turkish, Ukrainian.

All other languages work as in the original SubSync.

## Credits

- Based on [SubSync](https://github.com/sc0ty/subsync) by Michał Szymaniak, licensed under GPL-3.0, like this release.
- Speech recognition uses [faster-whisper](https://github.com/SYSTRAN/faster-whisper) and OpenAI's Whisper `small` model.
