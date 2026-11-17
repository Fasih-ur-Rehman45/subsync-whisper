# How the accuracy tests are done

The results in the README come from the tests described here. They measure one thing: **how far each synchronized line starts from where it should start**.

## The method

1. **Answer key.** A subtitle file whose timing is right for that exact copy of the film.
2. **Mistimed copy.** The answer key with a known timing error applied to every line (see the table below). The text is never changed.
3. **Sync.** SubSync syncs the mistimed copy to the film, exactly as a user would (the command line, or the built package in the end-to-end tests), with default settings.
4. **Score.** Every line of the result is paired with its line in the answer key, and the difference of their start times is its error.

| Error applied | Video time = | Used for |
|---|---|---|
| Standard | 1.04271 × file time + 9.4 s (23.976 → 25 fps, plus a delay) | Japanese films, Sita Sings the Blues, English films |
| Squeezed | 0.95904 × file time + 14.2 s (25 → 23.976 fps) | 2 Japanese films, instead of the standard one |
| Unusual speed | 1.0123 × file time + 6.5 s (not a frame-rate conversion) | Japanese films (`.odd`) |
| Near-standard | 1.0425 × file time + 9.4 s | 3 Japanese films (`.near`) |
| Different cut | Lines from mid-film on 45 s later (an extra scene), then the standard error | Japanese films (`.cut`) |
| Short video | 25 / 23.976 × file time + 2.5 s | Tears of Steel |

## What is reported

- **Within 0.2 s:** the share of lines whose error is at most 0.2 s, which isn't noticeable when watching. A line missing from the result counts as wrong.
- **Average error** and **worst line:** of the absolute errors.
- **Bias:** the average signed error. A bias close to the average error means the whole file moved by the same amount.
- **Time:** wall-clock time of the sync, from start to the saved file.

**Timing style.** Subtitle files differ in where they put a line against the speech: some show it about 0.3 s before people speak, others when they start, or a little after. SubSync puts lines a fixed lead before the detected speech (0.25 s, or 0.15 s for English films; values measured on 26 correct files). When a file's own style differs, every line comes out moved by about the same amount, with a small spread. Those results are reported as "timing style", separately from errors, and the README says so for each one.

**Checking the answer key.** Where it was done (Sita Sings the Blues, the English films), the correct file is synced as it is first: a right key barely moves. Two English films were left out because their files didn't fit those copies of the films.

## Test sets

| Set | Films | Reproducible by anyone |
|---|---|---|
| Japanese audio, English subtitles | 9 commercial films, 26 cases | No: the films can't be shared |
| Other subtitle languages | Spanish and Polish machine translations on 3 Japanese films; real Portuguese, Bulgarian and French subtitles on English films | No |
| English films, English subtitles | 11 commercial films | No |
| Short film | Tears of Steel (Blender Foundation, CC-BY), official subtitles in 6 languages | **Yes**: `tests/e2e/tears_of_steel.py` |
| Full-length film with songs | Sita Sings the Blues (public domain), community subtitles in 5 languages, song lines scored separately | **Yes**: `tests/e2e/sita_sings_the_blues.py` |

The two reproducible tests download the film and subtitles themselves and run on both release packages (Windows and Linux) before every release; a release is published only when they pass. See [Building, testing and releasing](development.md) for the commands.

## Rules for changes to the sync

Every change to the timing logic is checked on the 26 Japanese cases, Tears of Steel and Sita Sings the Blues before it is committed, and the changelog says how the results changed. Transcripts are cached, so a rerun after a change uses the same Whisper output and shows only the effect of the change.

## Machines

- Laptop: AMD Ryzen 9 5900HX, 8 GB of RAM, no graphics card used, Windows 11. Times in the README are from this laptop.
- GitHub Actions: `windows-latest` and `ubuntu-22.04` runners.

Whisper's output can differ slightly between processors: the same film may be split into transcript lines differently. The end-to-end tests run on both platforms for that reason.

## Limits

- The mistimed copies are made by a formula, so they test the errors real files have (frame rate, delay, an added scene), not every way a real file can be wrong.
- Only two test films are free to share; the larger sets can't be rerun by others.
- Japanese audio is tested only with English and translated subtitles, and with one Japanese subtitle file.
