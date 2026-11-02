# Architecture

Kirlian Terminal is an album-first terminal music player for macOS and Linux: one
Python 3.12+ package with a Textual interface, an owned mpv process driven over JSON
IPC, Mutagen tags, Pillow artwork, and an application-owned SQLite database (platformdirs
data directory or `--data-dir`). No services, plugins, or daemons; it never calls the
other Kirlian application.

## Boundaries

- Local playback works offline, with no account or key; audio stays on the computer.
- The only network call is the opt-in song-notes request. It sends title, artist,
  album, year, and language to the provider the listener chose, never audio,
  artwork, or paths, and never before notes are turned on.
- Music files, tags, and folder organization are only read, never written.
- Streaming, downloads, lyrics, cloud sync, and Kirlian visual generation are out
  of scope. Essential controls never depend on artwork, color, motion, or a mouse.
- GPL-3.0-or-later, consistent with Mutagen's GPL-2.0-or-later; see [licensing](licensing.md).

## Code map

| File (in `src/kirlian_terminal/`) | Responsibility |
| --- | --- |
| `__main__.py` | Options, mpv and database prerequisite checks, data path, diagnostics |
| `app.py` | Textual app: layout, key actions, workers, player events |
| `browse.py` | What each view lists (rows, heading, summary) from plain data |
| `dialogs.py` | Modal screens: folder, names, playlist picker, confirm, song-notes settings |
| `playback.py` | Owned mpv process, IPC replies, observed `PlaybackState`, queue commands |
| `library.py` | Read-only tag parsing, album identity, folder scan, tracks and settings |
| `playlists.py` | Saved playlists with ordered, duplicate-preserving entries |
| `picker.py` | The system folder picker (Finder, zenity, kdialog), offered only where one can open |
| `stores.py` | Stream-or-buy search links, built locally from album tags |
| `resume.py` | The saved listening place: queue, current song, position |
| `marquee.py` | Scrolling a clipped title in the highlighted row |
| `artwork.py` | Embedded and folder cover lookup with bounded decoding |
| `cover.py` | Cover widget: native, blocks, or off, with aspect-fit sizing |
| `graphics.py` | Renderer selection; Kitty adapter (pixel transport, targeted cleanup) |
| `terminal_support.py` | Bounded terminal version query before Textual owns input |
| `artwork_check.py` | `--check-artwork`: isolated native-image versus block comparison |
| `palette.py` | Ribbon colors from the playing album's artwork |
| `patterns.py` | The 180-pattern catalog: Braille geometry, depth, sound response |
| `animations.py` | Versioned pattern codes, session shuffle deck, animation clock |
| `visuals.py` | Ribbon widget, pattern reveal, progress line, title-rhythm loading state |
| `audio.py` | mpv filter graphs, level parsing and smoothing, speed and pitch |
| `amp.py` | Display-only amp panel and the Sound settings screen |
| `facts.py` | Song-notes providers, response readers, source check, keys, cache |
| `facts_check.py` | `--check-facts`: one live provider request, explained |
| `i18n.py`, `locales/` | Language detection, JSON catalogs, `_` / `n_` / `N_` |
| `appearance.py` | Validated appearance preferences and the three themes |
| `brand.py` | The one-line type mark (`✺  kirlian`; `*` in ASCII mode) |
| `styles.tcss` | Layout and initial colors |
| `scripts/` (repository root) | `preview_patterns.py` (catalog to SVG), `benchmark_patterns.py` (frame cost), `i18n_catalog.py` (string extraction, catalog gaps, placeholder checks) |

## Playback

`Player` starts mpv with `--no-config --load-scripts=no --idle=yes --no-terminal
--no-video --audio-display=no --ytdl=no --access-references=no
--input-default-bindings=no --pause=yes --volume=50 --loop-playlist=no
--loop-file=no`, the meter filter (see Amp and sound), and an IPC socket in a private
temporary directory. Arguments are a list, never a shell string; commands are JSON
with a request id and a three-second reply timeout.

Playback state is never simulated. Observed properties (pause, idle, position,
duration, volume, playlist and index, path, codec, bitrate, audio parameters) and the
`start-file`, `file-loaded`, and `end-file` events update `PlaybackState`, which the
app receives as messages. Each `file-loaded` increments a serial, so a repeat play of
one file counts as a new song. A closed connection becomes idle with an error.

The active queue is mpv's playlist; browsing, search, and playlist editing never
change it. Enter on a track, in any view or search result, plays its album in order
from that track; Enter on a playlist entry plays that playlist's available entries
in saved order from there. Both pause mpv, load with `replace` and `append`, select
the index, and resume. Append never interrupts and keeps duplicates; Enter on a queue
row jumps there. One lock serializes queue commands so rapid actions cannot
interleave a half-loaded queue. Shuffle and repeat are off. Quitting sends `quit`,
then terminates and finally kills the stored child handle; no process is ever found
or stopped by name.

## Library

The first launch asks for a folder. Later launches read the stored library without
scanning; `r` or `--music` starts a scan, and so does the first launch after an
upgrade that sets the `rescan` setting. A thread worker walks the folder for MP3,
FLAC, M4A, AAC, Ogg, Opus, and WAV files and reads tags with Mutagen, committing and
reporting about every 0.15 s so albums appear during indexing. Unreadable files are
skipped and counted; missing files are marked unavailable, not deleted.

Album identity hashes the release folder, casefolded album artist, and casefolded
album title, plus the MusicBrainz release id when the tags carry one (without it,
ids are unchanged). Disc folders (`CD 1`, `Disc 2`) count as their parent release and
supply a missing disc number. Editions in separate folders stay apart even with
identical tags; in one flat folder only the release id can separate them. Compilations default the
album artist to "Various Artists". Tracks sort by disc, numeric track, then path.
Title and album fall back to the filename and folder; `tracks.tagged` records whether
both came from tags. Adding that column sets `rescan`, which a complete scan clears,
so older libraries are rescanned once in the background instead of losing song notes.

Connections open and close per operation; write-ahead logging lets the interface
read committed batches mid-scan. Tables use `IF NOT EXISTS`; later columns need an
explicit upgrade, as `tagged` has. Playlist moves and appends run in one
`BEGIN IMMEDIATE` transaction, so rapid key presses never act on a stale order.

| Table | Contents |
| --- | --- |
| `settings` | Folder, appearance, artwork mode, saved patterns, amp, notes on/off and providers |
| `tracks` | One row per path: tags, album id, disc, track, duration, year, format, `available`, `tagged` |
| `playlists`, `playlist_entries` | Names; entries with their own id (so duplicates stay distinct), position, path |
| `facts` | Song-notes cache (see Song notes) |

## Interface and concurrency

Scanning, artwork, palettes, playlist and cache queries, provider requests,
preference saves, and opening a source URL run in workers or threads; the event loop
does only small settings reads and writes itself. Late results are dropped by guards:

| Work | Guard |
| --- | --- |
| Cover decode | `cover_revision`, after a 40 ms navigation debounce |
| Ribbon palette | `palette_revision`, tied to the playing album |
| Native image preparation | Request key of image, size, bounds, and cell size |
| Playlist entries | Kept only if the same playlist is still open |
| Song notes | `fact_revision`, bumped on song change and when notes turn off |

A language switch recomposes the screen while mpv keeps reporting. During it,
`rebuilding` makes player events, level readings, worker results, and status
messages update app state only; `apply_language` then redraws from state. Code that
touches widgets from events, workers, or timers must respect this flag.

Text input takes priority: while an `Input` has focus, `check_action` permits only
back and focus movement, so letters and Space never reach playback. Modal screens own
their keys; the amp panel never takes focus. Escape leaves search and restores the
previous view and row. Amp changes are diffs spread over several mpv commands;
`amp_lock` applies them, and filter reinstalls, strictly in order.

## Artwork and graphics

Embedded pictures come first (front covers preferred; ID3, FLAC, MP4, Ogg), then
`cover`/`folder`/`front`/`album`/`artwork` `.jpg`, `.jpeg`, `.png`, or `.webp` in
the track or parent release folder. Only JPEG, PNG, WebP, GIF, and BMP decoders run,
so Pillow's EPS reader never hands tag data to Ghostscript. Inputs are capped at
12 MiB and 16 million pixels (bomb warnings are errors) and shrink with Lanczos to
1024 pixels per edge; any failure means "no artwork", and nothing touches disk.
Memory caches hold 12 decoded covers, 12 prepared Kitty images, 12 `NO_COLOR`
grayscale copies, and 64 ribbon palettes; a scan clears covers and palettes.

`CoverImage` modes are `native` (textual-image's detected renderer: Kitty through
Kirlian's adapter, or Sixel), `blocks` (half-cell characters), and `off`. `auto` is
native when the startup probe found a protocol, except that automatic Kitty falls
back to blocks under Warp and when the terminal's version reply is the generic
`libghostty` identity. `TERM=linux` defaults to blocks. `--artwork` overrides one
launch; `c` switches and saves the mode.

The Kitty adapter prepares pixels in a cancellable worker and sends zlib-compressed
RGBA (`f=32`) in base64 chunks of at most 4096 characters, so no terminal PNG decoder
is needed. Placeholder colors encode image ids, so the adapter bypasses line filters
and the app keeps truecolor output; under `NO_COLOR` the pixels are grayscaled
instead. Cleanup deletes only owned image ids. See [terminal compatibility](terminals.md)
for per-terminal expectations, multiplexers, and `--check-artwork`.

## Ribbon patterns

The three-row ribbon spans the player (at most 400 columns) in Braille dots or ASCII.
The catalog has 180 patterns, 18 families × 10 named profiles, saved as
`v2:<family>:<profile>` codes. Families are only appended, so saved codes keep their
drawing; changing a recipe requires a new version. Saved `v1` filament and ripple
seeds still render exactly. The shuffle deck (every pattern before refilling,
preferring a new family) is session state.
The clock accumulates active wall time, not audio position, so seeking never jumps
the pattern; pause, loading, idle, Still, and Off stop the 10 Hz timer. A new song or
`x` dissolves the old pattern dot by dot over 0.7 s and briefly shows the new name.
Colors come from the playing album's artwork, else the interface palette.

While a song plays and the ribbon moves or the amp is open, a worker reads mpv's
meter about 20 times a second. `Reaction` smooths it into the animation rate
(0.45×–1.85× by energy), a brightness lift, flux-based sparks, and a `Sound` (bass,
mid, treble, energy, hit, pulse) that each family answers in one parameter; without
measurements a pattern draws exactly its saved shape. A reveal frame measured about
7 ms at 400 columns. See [patterns](patterns.md) for the catalog and benchmarks.

## Amp and sound

All processing happens in mpv's filter list; the app never decodes audio. The
`@meter` lavfi graph forces stereo, splits a mono copy through twenty half-octave
`bandpass` filters (40 Hz to 16 kHz), merges them as extra channels, measures every
channel with `astats`, drops the extras with `pan`, and adds `aspectralstats`
(centroid, flux). What plays is the stereo signal unchanged (mono on both sides,
surround folded); readings come from the `af-metadata/meter` property.

When on, the equalizer is an `@eq` graph of ten `equalizer` bands (31 Hz to 16 kHz,
±12 dB), a `volume` preamp (−12 to +6 dB), and `stereotools` balance ahead of the
meter; when off it is absent, not neutral. Toggling rebuilds the list with `af set`;
other changes use `af-command` on the running filters, and the list is reinstalled
while the next song loads if live tuning changed it (mpv rebuilds from the installed
list). ReplayGain is mpv's `replaygain`. Amp settings persist 0.3 s after a change.
Speed (0.5×–2×, key kept), pitch (±12 semitones), and Tape (pitch follows speed) use
mpv's `speed`, `pitch`, and `audio-pitch-correction` and are session-only.
Returning pitch to 0 removes mpv's tempo filter; a null test against untouched
playback is bit-exact afterwards. Rubber Band (`af=rubberband`) was measured as an
alternative and left out: on a steady tone at +3 semitones it added sidebands at
−28 dB against −62 dB for mpv's built-in shift. Preamp and balance are saved, so the
amp line names them whenever they are not neutral, and `R` on the Sound screen resets
every setting at once.

## Song notes

Notes are opt-in: the `facts` setting must be `on`, which only the notes settings
screen (`i`) sets; an environment key alone never enables them. Two seconds after a
song starts, providers are tried in the listener's order. Files without title and
album tags are never asked about, since filename stand-ins are never sent.

| Provider | Endpoint | Retrieved pages read from |
| --- | --- | --- |
| Exa | `/answer` with `outputSchema` | `citations` |
| OpenAI | `/v1/responses` with `web_search` | URL citations and search sources |
| Parallel | `/v1/responses`, low effort | URL citations and opened pages |
| Perplexity | `/v1/agent`, fast effort | Search results |
| Anthropic | `/v1/messages` with web search (5 uses) | Search results and text citations |

All providers get one question and return one JSON shape: up to three notes with
headline, body, kind (`story`, or `reading` labeled as interpretation), and source
URL. A shared check keeps a note only when its URL matches a page that provider's
search actually retrieved (ignoring scheme, `www.`, trailing slash); a model-written
URL alone is never shown. OpenAI and Anthropic allow a model override. Requests use
`urllib` in a thread with a 90-second timeout, resent once only if the connection
drops before any reply.

Before any request, `FactCache.saved` looks for an answer to the song in the current
language from any provider and any prompt version (notes over "nothing found", then
the current prompt, then the listener's order); if one is found, nothing is sent. Each
request is billed to the listener, so saved answers are never discarded: not on
reordering providers, recovering a failed primary, or changing the prompt. A failure
or missing key moves to the next provider. Failures are not retried until the settings screen
closes, except dropped connections, which retry on the next play. The cache key is
prompt version, provider, language asked in, and casefolded artist, album, and title.
The card follows the playing song and hides while the record pane shows another album.

Keys come from the provider's environment variable, then a session-only value, then
the OS credential store via `keyring` (session-only without one). They never enter
SQLite, logs, reports, or the repository, and are never displayed; turning notes off
keeps them. Textual prints worker tracebacks with local variables, so the two workers
holding a key use `exit_on_error=False`, and bad replies become `FactsError`.

## Internationalization

The interface ships in English, Spanish, French, German, Italian, Brazilian
Portuguese, Japanese, Korean, and Simplified Chinese: JSON catalogs keyed by English
source strings (missing entries fall back), named `str.format` placeholders, and
per-language plurals in `n_`. A saved choice wins, else `LC_ALL`, `LC_MESSAGES`,
`LANG`; Traditional Chinese and unlisted languages use English. A new language applies
live under `rebuilding` without touching mpv, the queue, library, view, or caches, and
re-requests the playing song's notes. Tags, filenames, provider text, pattern, provider,
and model names are never translated; the CLI, `--check-facts`, and key names stay English.

## Security and untrusted input

- Tags, filenames, playlist names, and provider text are untrusted; displayed text
  passes through `display_text`, which replaces terminal control characters.
  Provider text is also clipped, and only `http`/`https` sources are shown.
- Images are bounded by size, pixels, and format; terminal replies by a total
  deadline and byte cap. mpv runs without config, scripts, references, or ytdl.
- Diagnostic reports omit music, local paths, keys, and multiplexer socket or pane ids.

## Picking up where you left off

`resume.Place` is the queue's paths, the current index, and the position, stored as
the `resume` setting. `remember_place` writes it from mpv's reported state when the
queue or song changes or the position moves 5 s, and exactly on quit: one small
settings write, like other preferences. On launch, after mpv starts, files that have
gone are dropped and `Player.resume` loads the saved song alone, paused, waits for
`file-loaded`, seeks, then appends the rest of the queue and moves the earlier songs
in front, so the seek can never land on another song still loading. Saving is
suspended while a resume assembles the queue, so a half-built queue is never stored.

## Long titles

`marquee.Marquee` scrolls the highlighted row's main cell when its text is wider
than the column (0.2 s per character after a short hold) and restores the original
`Text` when the cursor moves or the table rebuilds. It only runs with gentle motion.

## Playbar, stores, album notes, amp placement

- **Playbar.** `visuals.Transport` renders clickable controls with Textual `@click`
  actions bound to the same app actions as the keys, so clicks and keys can never
  disagree. `Progress` seeks on release with `seek <percent> absolute-percent+exact`;
  while dragging, player updates do not move the knob.
- **Stores.** `stores.py` builds each store's public search URL from the album's
  artist and title; no API, nothing sent until the listener picks a store, and only
  for fully tagged albums.
- **Album notes.** The same providers, source check, and cache as song notes, with
  a second question (`album_question`) under a key no song key can collide with
  (`album_key`). Each album is asked once, after the song; failures stay quiet
  because the song's status already reports the provider's state. The song question
  is unchanged, so earlier saved answers stay valid. `FactsConfig.albums` turns
  them off.
- **Amp placement.** Two `AmpPanel` instances, the playbar one and a `mini` one in
  the record pane, receive the same settings; only displayed panels read levels.
  `place_amp` chooses by `Appearance.amp` and falls back to the playbar when the
  record pane is hidden. `RecordPane.on_resize` sizes the cover from the measured
  heights and margins of everything else it shows.
- **Saving never ends the session.** Workers that write to SQLite run with
  `exit_on_error=False`; `on_worker_state_changed` reports database and disk errors
  in the status line. The few synchronous writes catch `sqlite3.Error` themselves.

## Distribution

Listeners install with `curl -fsSL …/releases/latest/download/install.sh | sh`. The
installer (`packaging/install.sh`) is POSIX `sh` in plain ASCII, so it runs under any
locale. It relies on uv rather than a Homebrew formula or PyPI: uv brings its own
Python 3.13 and isolates the app, and `uv tool install` gives updates by rerunning.
mpv comes from Homebrew on macOS; on Linux the installer prints the package command,
because it never runs sudo. The release workflow renders the installer with the
version and the wheel's SHA-256 and attaches both to the release. The download is
checked before anything is installed. The version lives only in `pyproject.toml`;
`__version__` reads the installed package metadata. Homebrew stays possible later; a
formula in homebrew-core needs a public, established project.

## References

- [Textual workers](https://textual.textualize.io/guide/workers/)
- [Textual testing](https://textual.textualize.io/guide/testing/)
- [mpv JSON IPC and commands](https://mpv.io/manual/stable/#json-ipc)
- [Mutagen](https://mutagen.readthedocs.io/en/latest/)
- [uv projects](https://docs.astral.sh/uv/guides/projects/)

These references describe dependencies. [Testing](testing.md) records what has been
verified, and what is [not yet verified](testing.md#not-yet-verified).
