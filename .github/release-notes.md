<!-- Release page template. The release workflow replaces {{VERSION}} with the
     version and {{CHANGES}} with that version's section of CHANGELOG.md.
     Keep it a short overview: the full guide is README.md. -->
SubSync synchronizes subtitles to a video's audio. This version adds **Japanese audio** and many more languages with the Whisper speech recognition model, so English subtitles can be synchronized to Japanese films, and subtitles in other languages to films in Japanese or English.

## What's new

{{CHANGES}}

## Get started

1. **Windows:** download **`subsync-{{VERSION}}-portable-amd64.exe`** below and run it to unpack SubSync, then run **`subsync.exe`** in the new `subsync` folder (or use the zip). **Linux:** download **`subsync-{{VERSION}}-linux-x86_64.tar.xz`**, unpack it and run **`./subsync/subsync`**.
2. Choose your subtitles and the video, then click **Start**. SubSync detects the audio language.
3. The first time, SubSync downloads its speech model (about 490 MB, once), and for subtitles in a language other than English, its translation model (about 490 MB, once).

Needs 64-bit Windows 10 or 11, or 64-bit Linux (Ubuntu 22.04 or newer and similar), and 8 GB of RAM. If Windows shows *"Windows protected your PC"*, click **More info**, then **Run anyway**. To check a download, compare its checksum with `SHA256SUMS` below ([how](https://github.com/Z0rdic/subsync-whisper/blob/master/SECURITY.md#release-files)).

**[Full guide](https://github.com/Z0rdic/subsync-whisper#readme)**: using it, what the messages mean, test results, known limits and troubleshooting.
