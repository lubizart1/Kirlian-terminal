# Kirlian Terminal

A small terminal music player for people who listen to albums.

Kirlian Terminal plays local music, keeps your place in the record, and is being
built as a standalone companion to Kirlian. Playback is offline. No account or API
key is required, and the player does not modify your music files or tags.

**Status: local prototype with the filament listening interface.**
Includes background indexing, album/artist/song browsing, search, an active queue,
keyboard playback controls, local covers, a filament ribbon, the Kirlian header,
and local appearance preferences.
See the [verification record](docs/development.md)
for actual checks and remaining limitations. macOS and Linux are the intended platforms.

## Install and run

Requires Python 3.12+, [uv](https://docs.astral.sh/uv/getting-started/installation/),
and [mpv](https://mpv.io/installation/). Install the playback engine first:

```sh
# macOS with Homebrew
brew install mpv

# Debian or Ubuntu
sudo apt install mpv
```

On other Linux distributions, install mpv with your package manager.
From a checkout of this repository:

```sh
uv sync --locked
uv run kirlian
```

Enter your music folder when prompted, open an album with Enter, and press Enter
on a track to play. Albums appear as indexing progresses. Later launches use the
saved library; press `r` when you want to rescan.

You can also choose the folder on launch:

```sh
uv run kirlian --music "$HOME/Music"
```

Passing `--music` requests a scan on that launch. To use an isolated library for
testing, add `--data-dir .local/tryout`. Run `uv run kirlian --help` for options.

## Listening

| Key | Action |
| --- | --- |
| `j` / `k`, up / down arrows | Move selection |
| `h` / `l`, left / right arrows | Back / open |
| `Enter` | Open a collection or play a track |
| `Space` | Play / pause; start an idle queue |
| `/` | Search songs, albums, and artists |
| `Esc` | Leave search or go back |
| `Tab` / `Shift+Tab` | Change pane |
| `a` | Append selected song or album without interrupting playback |
| `n` / `N` | Next / previous track |
| `H` / `L` | Seek backward / forward five seconds |
| `-` / `=` | Lower / raise volume |
| `v` | Turn animation off / on; remembered between launches |
| `x` | Choose a new animation without changing the song |
| `s` / `S` | Save the current animation / cycle through saved animations |
| `c` | Switch cover display between terminal graphics and compatible blocks; remembered |
| `f` / `r` | Choose folder / rescan |
| `p` | Preview and save appearance preferences |
| `?` | Keyboard help |
| `q` | Quit and stop this player's audio |

The bottom row shows the current Enter and Space actions, pattern, help, quit,
and volume. Search and personalization stay in the header; Help lists the other
controls. Collection headings and counts share a row, and status messages appear
only when there is something to report.

Typing in search or the folder field takes priority over these shortcuts.
Search does not stop playback; Escape restores the previous view and selection.
Playing a search result starts its album queue at that song. Enter on a Queue
item jumps to it. `>` marks the current track; the highlighted row is your selection.

The player reads MP3, FLAC, M4A/AAC, Ogg Vorbis/Opus, and WAV candidates. Playback
depends on your installed mpv decoders and the file itself. Unreadable files are
summarized during scanning; playback failures appear in the status line.

## Covers and the filament ribbon

The record pane reads embedded covers first, then `cover`, `folder`, `front`,
`album`, or `artwork` images (JPG, JPEG, PNG, WebP) beside the album. Disc subfolders
also check their parent. There are no cover downloads. A missing or unreadable
image leaves the record's text visible. The pane hides below 110 terminal columns.

Image rendering uses [textual-image](https://pypi.org/project/textual-image/).
Automatic mode uses native images when supported and colored character blocks
otherwise. Ghostty is no longer forced to use blocks. Native images preserve the
source up to 1024 pixels per edge, then scale to the physical display area. Low
resolution source covers cannot gain detail. Kitty-compatible rendering sends
compressed RGBA pixels, so covers do not depend on the terminal's PNG decoder.

Cover decoding and native image preparation run in background workers. Recent
Kitty covers stay cached in memory and in the terminal, so revisiting them or
repainting the interface does not upload them again. These caches are bounded;
switching to blocks or quitting releases the native images. Nothing is written
to your music folder. See the [performance checks](docs/development.md#2026-10-13-cover-latency-and-interface-responsiveness)
for measured results and their limits.

The header is drawn entirely with terminal characters: an open sunburst and
lowercase dotted lettering, using the same Braille grid as the filament. It needs
no image support or custom font. Plain ASCII pairs a punctuation emblem with
ordinary lettering; short windows use a one-line mark. Choose Drawn or Simple
wordmark under `p`.

Owner-provided screenshots confirm sharp covers in the standalone Ghostty app
and block covers in Herdr. After the Herdr setup work, the owner reports success
and supplies a new screenshot with a sharp cover and character header. The
screenshot does not include terminal identity; see the
[compatibility record](docs/terminals.md) for the scope of these observations.

Press `c` to compare native graphics with blocks; your choice is remembered. To
override a saved choice for one launch:

```sh
uv run kirlian --artwork native
# Or return to capability detection:
uv run kirlian --artwork auto
# A deliberate text fallback:
uv run kirlian --artwork off --characters ascii
```

`NO_COLOR` produces grayscale covers without corrupting native image identifiers.
A forced native mode can still be blank in an unsupported terminal; use `c` or
relaunch with `--artwork blocks`. See the [terminal compatibility notes](docs/terminals.md)
for verified checks and remaining gaps.

If native artwork stays blank, quit the player and run `uv run kirlian --check-artwork`.
The version 2 check compares uncompressed RGB (A), uncompressed RGBA (B), compressed
RGBA (C), PNG (D), the player's native placement (E), and block artwork (F).
Enter the letters you can see; it prints terminal replies and settings. Add
`--artwork-report .local/artwork-report.json` to save a local report, including the
running terminal's version reply and loaded code fingerprints. The check uses a
generated picture, opens no music library, and changes no preferences. A terminal
reply of `OK` alone does not prove that the picture was visible.

A reply of `libghostty` identifies an embedded engine rather than the standalone
Ghostty app. Its host can accept image commands without displaying them. Automatic
mode conservatively uses block covers for that identity. Use `--artwork auto`
to override a previously saved native choice. In Herdr, enable its Kitty graphics
setting and reattach the client, then test `--artwork native`. Herdr 0.8.2 uses
`[experimental] kitty_graphics = true`; newer releases document a `[terminal]`
setting. Tmux uses a separate passthrough mechanism. See
[multiplexer setup](docs/terminals.md#multiplexers) for exact configuration and
verification limits.

Linux terminal apps can use native artwork when supported. The bare Linux virtual
console defaults to block artwork and an ASCII ribbon; disabling covers is optional.

The three-row **filament ribbon** spans the player beneath the title and artist.
Fine Unicode Braille dots give it a smaller drawing grid than ordinary characters.
It is text, rather than a raster animation. The separate thin line shows actual
playback progress. The ribbon's highlighted portion follows progress too, but
its shape is procedural decoration, **not an audio waveform**.

Ribbon colors come from the **playing album's artwork**, with up to three quiet
colors blended along the filament. Dark colors are lifted for readability. Browsing
another album does not recolor the playing song, and the palette still works with
block covers, a hidden record pane, or artwork display turned off. Missing artwork
uses the selected interface palette; monochrome covers stay neutral. `NO_COLOR`
still renders the interface in grayscale. Everything is extracted locally.

There are **100 patterns: ten motion families with ten variations each**. Filaments,
tides, braids, ripples, orbits, fronds, mycelium, embers, seeds, and constellations
share the same quiet, three-row area. [Explore the pattern catalog](docs/patterns.md).
Each new song draws from a shuffle pool that visits all 100 before refilling and
prefers a different family next. `x` draws another pattern from the same pool,
`s` keeps it, and `S` recalls saved patterns from their beginning. Pattern names
appear when shuffling or saving. Existing saved filament and ripple seeds retain
their original drawings.

Seeking keeps the pattern; pause freezes it. Motion runs at most 10 times per
second and stops ticking when paused, loading, idle, still, or off. The region
retains its height when hidden. Patterns are generated locally without model calls.

## Make it yours

Press `p` to preview aubergine, sage, or amber for the interface; gentle, still, or no motion; fine
dots or plain ASCII; and the drawn or simple character wordmark. The current
song and queue keep playing. **Save changes** or `Ctrl+S` saves locally; **Cancel**
or Escape restores the previous appearance. **Reset** previews the defaults without
saving them. The screen labels unsaved previews and confirms a successful save.
If saving fails, your preview stays open so you can retry or cancel.
Tab moves between controls and Enter opens a choice. Escape closes an open choice
before leaving the page. In small windows the settings list scrolls.

A sample selection and shortcut row show the interface accent immediately. The
filament keeps the playing album's colors. Gentle motion stays still when playback
is paused or stopped, short windows use the compact header, and `NO_COLOR` keeps
colors grayscale; the settings screen explains these limits when they apply.
Saved preferences apply to later launches using the same data directory. An explicit
`--characters` argument still overrides the saved character choice for that launch.

The folder prompt remains a single step: select a local folder and listen with
defaults, then personalize whenever you wish. No account or setup wizard is needed.

## Local data and privacy

Music, tags, and artwork are never written to. The application stores metadata,
the chosen folder, file availability, cover display choice, appearance preferences, and saved seeds in its
own SQLite database:

- macOS: `~/Library/Application Support/kirlian-terminal/`
- Linux: `$XDG_DATA_HOME/kirlian-terminal/`, defaulting to `~/.local/share/kirlian-terminal/`

`--data-dir` overrides that location. This prototype selects one music root at a
time. Playback uses a private local socket and one owned mpv child process. There
are no accounts, analytics, network services, or paid API calls in Milestone 1.

## Current limits

- Saved playlist editing, optional song facts, and listening-position restoration
  are not implemented. The Playlists view states this; Queue is available for the
  current session.
- Relaunching retains the library, but clears the active queue and starts stopped.
- Album identity uses tags and release folders. Discs in `CD 1` / `Disc 2` style
  subfolders share the parent folder. Distinct editions with identical tags in one
  flat folder cannot reliably be separated. Unknown artists in untagged mixed
  folders also need better source organization for accurate grouping.
- Long titles are clipped in the table; the context pane provides more space on
  wider terminals. It hides below 110 columns. The minimum target is 80 × 24.
- Audio quality and gapless album transitions need a human listening check.

## Project notes

- [Product specification](docs/specification.md): supplied handoff and release boundaries.
- [Architecture and decisions](docs/architecture.md): why the project is organized this way.
- [Development record](docs/development.md): changes, evidence, and remaining work.
- [Listening interface studies](docs/design-studies.md): accepted play bar, branding, and personalization direction.
- [Testing and listening](docs/testing.md): automated checks and a manual walkthrough.
- [Contributing](CONTRIBUTING.md): development and documentation expectations.

The first milestone covers local indexing, album browsing, search, and playback.
The owner has brought artwork, the filament ribbon, branding, and personalization forward. Saved
playlist editing and optional sourced song facts follow separately. Streaming,
downloads, lyrics, cloud sync, and visual generation are outside this release.

## License

MIT is the intended direction, confirmed by the owner; no license has been applied
yet. Mutagen, the current metadata reader, is GPL-2.0-or-later. An MIT-only distribution cannot be assumed
from a license on our own source. See the [license review](docs/licensing.md) for
dependency terms and the unresolved decision before publishing.
