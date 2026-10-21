# yt-dlp-gui

Simplistic graphical interface for the command line tool [yt-dlp](https://github.com/yt-dlp/yt-dlp).

> **Note**
> The upstream project [dsymbol/yt-dlp-gui](https://github.com/dsymbol/yt-dlp-gui) was archived by its maintainer and no longer accepts pull requests or releases.
> The last tagged release (`2025.09.30`) predates the deno dependency and the yt-dlp auto update that were already merged into `main`, so it no longer works with YouTube.
> This fork contains the fixes that are needed to make the application work again, see [Fixes in this fork](#fixes-in-this-fork).

## Usage

There are two ways to get started, depending on your preference and system:

* [`Portable`](#portable) ~ *Windows*
* [`Manual`](#manual) ~ *Platform independent*

### Portable

Download the latest build from the [releases of this fork](https://github.com/3155498108/yt-dlp-gui/releases/latest). This is a ZIP file containing the program files and all necessary dependencies.

*The upstream releases are outdated, see the note above.*

### Manual

You **must** have [Python](https://www.python.org/downloads/) 3.9+ installed.

```bash
git clone https://github.com/3155498108/yt-dlp-gui
cd yt-dlp-gui
pip install -r requirements.txt
cd app
python app.py
```

## Preset Customization (Advanced)

Want to create your own presets or modify existing ones? You're in the right section. customization options reside in the `config.toml` file. If a preset fails, check the `debug.log` file for details.

**Notes:** 
- All files mentioned are in the `yt-dlp-gui` root directory.
- The arguments specified will be added to the [base](https://github.com/dsymbol/yt-dlp-gui/blob/main/app/worker.py#L28) `yt-dlp` arguments.
- Prefer lists over strings for complex presets.

### Presets

Defined in the `[presets]` table. Each preset is a key‑value pair, the value can be provided as a string or list.

### Example

```toml
[general]
...

[presets]
...
mp4_thumbnail = ["-f", "bv*[vcodec^=avc]+ba[ext=m4a]/b", "--embed-thumbnail"]
```

## Fixes in this fork

The upstream repository was archived in March 2026 and the last tagged release does not contain the deno dependency and the yt-dlp auto update that had already been merged into `main`. A freshly installed copy therefore downloads an outdated yt-dlp, never installs the JavaScript runtime that YouTube needs and fails with `HTTP Error 403: Forbidden` or `Sign in to confirm you're not a bot`.

The following fixes are applied on top of `main`:

- the managed `yt-dlp`, `ffmpeg` and `deno` are put in front of `PATH`, a copy that is installed system wide can no longer shadow the managed one
- a failed dependency download no longer leaves the download button disabled and is reported to the user
- yt-dlp falls back to downloading the latest release when `yt-dlp -U` fails, it cannot update a pip installation and it needs the GitHub API
- `update_ytdlp = false` in `config.toml` is respected
- the error message of yt-dlp is shown in the download list instead of only `ERROR`
