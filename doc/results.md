# Test results and how it works

[Back to the README](../README.md)

## Speed and accuracy

The tests use deliberately mistimed copies of correct subtitles, and compare SubSync's result with the correct timing line by line. A 0.2 s difference isn't noticeable when watching. [benchmark.md](benchmark.md) describes the method: the timing errors applied, how lines are scored, which test sets anyone can rerun, and the limits.

**Japanese films with English subtitles** (9 films, about 2 hours each):

| Result | Films |
|---|---|
| **All lines within 0.2 s** of the correct timing, on average 0.04 s | 7 of 9 |
| 89–100% of lines within 0.2 s: a film with little dialogue (583 lines in 88 minutes) gives less evidence | 1 of 9 |
| Lines about 0.6 s early: this subtitle file shows every line about 0.3 s *after* people start speaking, unlike the others, which show lines just before | 1 of 9 |
| Subtitles made for a different cut, synced piece by piece: 90–100% of lines within 0.2 s; a few lines right at each cut can land on the wrong side | 6 of 7 |
| Subtitles made for a different cut that couldn't be confirmed, so no file was saved | 1 of 7 |

**Other subtitle languages** (from 0.20):

| Subtitles and audio | Result |
|---|---|
| Spanish and Polish subtitles (machine-translated test copies) on 3 Japanese films | **6 of 6 with all lines within 0.2 s** |
| Real Portuguese and Bulgarian subtitles on an English film | **2 of 2 with all lines within 0.2 s** |
| Real French subtitles on an English film | Lines about 1 s early: all of this film's subtitle files, even the English one, show lines after the speech starts |

**A short film** (from 0.20): the official English, Spanish, German, Italian, Dutch and Russian subtitles of [Tears of Steel](https://mango.blender.org) (a free 12-minute English film), mistimed as if made for 25 fps instead of 23.976 fps, plus 2.5 s:

| Result | Languages |
|---|---|
| **All lines within 0.2 s** of the official timing, 0.18 s after it: the official files show lines 0.33 s before people speak, SubSync 0.15 s | 6 of 6 |

**A full-length film with many songs** (from 0.21): [Sita Sings the Blues](https://sitasingstheblues.com) (a free 82-minute English film, about a third of its lines sung), with community subtitles in English, Spanish, Chinese, Czech and French, mistimed by a speed difference of 4.3% plus 9.4 s:

| Result | Languages |
|---|---|
| **All lines within 0.2 s**, song lines as well as dialogue (worst line 0.04–0.07 s) | 4 of 5 (English, Spanish, Chinese, Czech) |
| Every line 0.2–0.37 s from the file's timing: this French file shows lines about 0.3 s later than SubSync's "just before speech", throughout | 1 of 5 |

The speech detector counted about a quarter of the singing as speech; it didn't move any line.

**English films with English subtitles** (from 0.21), each film's own English file mistimed by the same 4.3% plus 9.4 s. These go through the original SubSync method, whose result is now checked and polished against the detected speech:

| Result | Films |
|---|---|
| **99.8–100% of lines within 0.2 s** (the few others are lines in the first 9 seconds, which this mistiming pushes before 0:00) | 7 of 11 |
| Every line moved by about the same 0.2–0.5 s against the file (at most 0.14 s apart): these files show lines after the speech starts, or 0.35 s before it | 4 of 11 |

Before the speech check, one of these films (Cars) had only 65% of lines within 0.2 s, because the original method stops listening once its answer looks good enough. Two more films were left out: their subtitle files don't match these copies of the films (one is 1.85 s early throughout, the other made for another frame rate).

Anyone can repeat both tests: see [Building, testing and releasing](development.md).

**Time,** on a laptop with an AMD Ryzen 9 5900HX processor and 8 GB of RAM, using no graphics card:
- Most films: 1.5–2.5 minutes the first time, seconds when syncing the same film again.
- Films with little dialogue: up to 6 minutes.
- Subtitles in a language other than English: 1–2.5 minutes more the first time, for translating them.

## How it works

SubSync transcribes only a few 5-minute parts of the film, spread from start to end. It fits the timing to them, then checks that timing against the speech detected in the whole film, stretch by stretch (about 15 minutes each). Stretches with too little dialogue to judge (fewer than 30 subtitle lines) aren't checked on their own. It stops as soon as the result is confirmed. That is why a 2-hour film takes minutes rather than the 15–30 minutes a full transcription would take. See [assets.md](assets.md) for details.

Videos under 30 minutes (TV episodes, short films) give less speech to measure the speed with, so they're split into at least 4 parts, and a speed difference is accepted only when it's a frame-rate conversion (between 23.976, 24, 25, 29.97 and 30 fps), which is then set exactly.

On 5.1 audio, Whisper listens only to the center channel, where the dialogue is, like the original SubSync does. Other channels can be chosen in the window where you choose the audio stream, under **Audio channels**, or with `--ref-channels` on the command line.

## Which languages work how

| Your subtitles and audio | What SubSync does | Tested |
|---|---|---|
| **English subtitles**, audio in Japanese or another language listed below | Whisper translates the speech to English and matches it with your subtitles | Japanese, 9 films |
| **Subtitles in the same language as the audio**, e.g. Japanese subtitles with Japanese audio | Whisper writes down the speech in that language and matches it with your subtitles | 1 Japanese film (97 minutes) whose subtitles were already correct: confirmed after 2 of 20 parts, every line kept within 0.08 s |
| **Subtitles in another language**, audio in Japanese or another language listed below (from 0.20), e.g. Spanish subtitles with Japanese audio | Whisper translates the speech to English, and your subtitles are translated to English on your computer, only for matching (they are never changed) | Spanish and Polish on 3 Japanese films |
| **English audio with subtitles in another language** (from 0.20), e.g. Japanese subtitles for an English film | Whisper writes down the English speech, and your subtitles are translated to English for matching | Real Portuguese, Bulgarian and French subtitles on 2 films |
| **English audio with English subtitles** | The original SubSync method first, its result then checked and polished against the speech detected in the whole film (from 0.21; kept as found when speech doesn't confirm it). If it can't sync them, Whisper writes down the English speech and matches it with your subtitles (from 0.20, when the speech model is already downloaded) | Tears of Steel: the original method saved nothing, Whisper got all lines within 0.2 s |
| Audio in the other languages the original SubSync supports (French, German and others) | The original SubSync method, unchanged, with its dictionaries for subtitles in another language | By the original project |

Translation needs a second one-time download (about 490 MB) and adds 1–2.5 minutes per film the first time; the result is kept, so syncing the same subtitles again is quick.

The audio language itself is detected with Whisper when the video doesn't say it. That was tested on 34 films in Japanese and English.
