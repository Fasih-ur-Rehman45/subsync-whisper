# Security

## Reporting a problem

Please report security problems privately: on the repository's **Security** tab, choose **Report a vulnerability**. Don't open a public issue for them. Say what is affected, how to reproduce it, and which version you used (shown in the About window, or by `subsync-cmd --version`).

You'll get an answer within a week. Fixes go into the next release, and the changelog says what was fixed once the release is out.

## Supported versions

Only the latest release gets fixes. The original SubSync (0.17 and older) is not maintained here.

## What SubSync downloads, and how it is checked

SubSync works offline on your computer: it never sends your videos, subtitles or transcripts anywhere. It downloads only these, and only after asking (or when run on the command line without `--offline`):

| What | From | How it is checked |
|---|---|---|
| Speech and dictionary files of the original SubSync method | The original SubSync's GitHub release (`sc0ty/subsync`, `assets`) | Signed by the original SubSync's key (`key.pub`, shipped with the app); a file whose signature doesn't verify is not installed. Zip archives are refused when any file in them would land outside the asset folder. |
| Whisper speech model (`small`) | Hugging Face, `Systran/faster-whisper-small` | Downloaded at a fixed revision (`536b066…`), so a change in that repository can't change what is installed. |
| Translation model (M2M100) | Hugging Face, `jncraton/m2m100_418M-ct2-int8` | Downloaded at a fixed revision (`7c1b262…`). |

Automatic updates are turned off: this version never replaces itself.

## Release files

Each release page lists a `SHA256SUMS` file with the checksum of every download. To check a file before running it:

```bash
sha256sum -c SHA256SUMS --ignore-missing
```

On Windows (PowerShell), compare the output of this with the line for that file:

```powershell
Get-FileHash subsync-<version>-portable-amd64.exe -Algorithm SHA256
```

Releases are built and published by the repository's GitHub Actions workflow (`.github/workflows/build.yml`), only after the end-to-end tests pass on the built packages.
