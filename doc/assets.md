# SubSync assets overview
Assets are downloadable packages used by SubSync. Currently, there are three types of assets:
- speech recognition model;
- dictionary;
- self updater.

Assets available on server are listed in [assets.json](https://github.com/sc0ty/subsync/releases/download/assets/assets.json).

## Dictionary
Used for translation subtitles when reference is in another language.
Languages are encoded in file name as `[lang1]-[lang2].dict`.
It is text file with one phrase per line with translations separated by `|`.
Lines beginning with `#` are omitted (commented out).
Example:
```
# Example dictionary file
phrase1|translation1
phrase2|translation2a|translation2b
```

## Speech recognition model
Used in text-to-speech conversion.
Consist of several files, including acoustic and language model, list of words and JSON description.
Description file is named as `[lang].speech` and contains model parameters.
This is the configuration for pocketsphinx library.
My knowledge about Sphinx models is very limited, I never created one by myself, just using publicly available ones.
If you created such model and want to share, please let me know and I will make asset for SubSync from it.

For more information please refer to CMUSphinx [docs](https://cmusphinx.github.io/wiki/).

## Languages without speech recognition model
There is no pocketsphinx model for many languages (Japanese, Korean, Portuguese, Polish, Arabic and others, see `languages` in `subsync/synchro/transcribe.py`).
Audio in these languages is transcribed with [faster-whisper](https://github.com/SYSTRAN/faster-whisper) instead, to a temporary subtitle file that is then used as a reference.
It is an optional dependency (`pip install faster-whisper`), the Whisper model is downloaded on first use.
If SubSync runs under Python too old for faster-whisper, transcription is run in a separate process, using the interpreter from `.whisper` directory next to the sources (or set by `SUBSYNC_WHISPER_PYTHON`).
When subtitles are in English, speech is translated to English by Whisper and no dictionary is used.
It is slower than pocketsphinx, so only as much audio is transcribed as needed:
- audio is scanned once, finding speech (with the voice activity detector bundled with faster-whisper) and quiet moments to cut it into chunks of about 5 minutes;
- chunks are transcribed in an order spread over the whole file (first, last, middle...);
- from the second chunk on, synchronization found by matching words is polished with speech of the whole file (best overlap of subtitle lines with detected speech, searched close to it) and checked in a much wider range; when speech confirms it, transcription stops.

Typically 2-3 chunks are needed. When speech never confirms the result, the whole file is transcribed. With effort set to 1.0 the whole file is always transcribed, and only then polished.
Transcript chunks and detected speech are cached in the system temporary directory (`subsync-transcripts`), so synchronizing against the same file again does not repeat the transcription.

Model could be selected with environment variables: `SUBSYNC_WHISPER_MODEL` (default `small`), `SUBSYNC_WHISPER_DEVICE` (default `cpu`) and `SUBSYNC_WHISPER_COMPUTE` (default `int8`).

Transcription could be also run separately, to create a reference for SubSync build without this feature:
```
python subsync/synchro/transcribe.py video.mkv
```
With `--translate` option English translation of the speech is written instead, useful as a reference for English subtitles.
