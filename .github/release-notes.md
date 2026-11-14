<!-- Release page template. The release workflow replaces {{VERSION}} with the
     version and {{CHANGES}} with that version's section of CHANGELOG.md.
     Keep it a short overview: the full guide is README.md. -->
SubSync synchronizes subtitles to a video's audio. This version adds **Japanese audio**, so English subtitles can be synchronized to Japanese films.

## What's new

{{CHANGES}}

## Get started

1. **Windows:** download **`subsync-{{VERSION}}-portable-amd64.exe`** below and run it to unpack SubSync, then run **`subsync.exe`** in the new `subsync` folder (or use the zip). **Linux:** download **`subsync-{{VERSION}}-linux-x86_64.tar.xz`**, unpack it and run **`./subsync/subsync`**.
2. Choose your subtitles and the video, then click **Start**. SubSync detects the audio language.
3. The first time, SubSync downloads its speech model (about 490 MB, once).

Needs 64-bit Windows 10 or 11, or 64-bit Linux (Ubuntu 22.04 or newer and similar), and 8 GB of RAM. If Windows shows *"Windows protected your PC"*, click **More info**, then **Run anyway**.

**[Full guide](https://github.com/Fasih-ur-Rehman45/subsync-whisper#readme)**: using it, what the messages mean, test results, known limits and troubleshooting.
