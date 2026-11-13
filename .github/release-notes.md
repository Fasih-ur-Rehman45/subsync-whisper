SubSync that also synchronizes to **Japanese audio** (and 34 other languages that have no SubSync speech model, e.g. Korean, Polish, Turkish), using the Whisper speech recognition model.

## Install

1. Download `subsync-<version>-windows-x64.zip` below.
2. Unzip it anywhere and run `subsync.exe` (or `subsync-cmd.exe` from a command prompt).

Needs 64-bit Windows 10 or 11, about 8 GB of RAM and 1.5 GB of disk space. No graphics card needed.

## First use

The first synchronization to Japanese audio asks to download the speech recognition model (about 490 MB). It needs internet once and is kept in `%USERPROFILE%\.cache\huggingface` for later use.

## What to expect

- **English subtitles to Japanese audio** take about 2–3 minutes per film on a recent laptop processor. Speech is translated to English and matched with the subtitles, then the timing is polished against detected speech.
- **The result is saved only when it is confirmed** by the speech and by every part of the film. Otherwise SubSync says it couldn't synchronize, instead of giving wrong timing.
- **Subtitles made for a different cut** (scenes added or removed) are synchronized piece by piece.
- Transcripts are cached in `%TEMP%\subsync-transcripts`, so syncing the same film again is quick. The folder can be deleted at any time.
- Other languages work as in the original SubSync.

## Known limits

- When the subtitle file itself shows every line too early or too late, the result keeps that habit.
- Films with very few subtitle lines take longer (up to about 6 minutes).
- Automatic updates are turned off. New versions appear on this page.
