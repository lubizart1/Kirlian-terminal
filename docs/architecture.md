# Architecture and decisions

## 2026-10-13: an independent local application

The supplied handoff selects Python 3.12+, Textual, mpv JSON IPC, Mutagen, SQLite,
platformdirs, and uv. Keep these choices unless a documented owner decision changes them; licensing of
the metadata dependency is now under review. The application does not import or call
the existing Kirlian backend. Playback needs neither a network connection nor a key.

One owned mpv process handles the entire queue and transitions. A persistent IPC
connection correlates command replies and observes playback properties. The UI
displays those observations. The socket lives in a private temporary directory;
shutdown targets the stored child-process handle, never processes found by name.

Library scans read tags in a background worker and write an application-owned
SQLite database. Connections are scoped to their thread. The UI gets incremental
updates while indexing continues. Music files are only read.

Album identity combines normalized album artist and title with the release folder.
Disc subfolders such as `CD 1` share their parent release folder. This deliberately
keeps editions in separate folders apart, even if their tags match. Folder identity
is a conservative heuristic, not a MusicBrainz release resolver.

The browser and the active queue are separate. Opening albums and filtering the
library never replace the queue. Only explicit play and append actions change mpv's
playlist. A song search result starts its ordered album queue at that song.

Textual input widgets own typing. Single-letter playback and navigation bindings
are disabled while a text input has focus. Escape leaves search and restores the
previous browser view and position.

## Code map

| File | Responsibility |
| --- | --- |
| `src/kirlian_terminal/__main__.py` | Command-line options, prerequisite checks, application data path |
| `src/kirlian_terminal/library.py` | Read-only tag parsing, grouping, scanning, SQLite persistence |
| `src/kirlian_terminal/playback.py` | Owned mpv process, command replies, observed playback state |
| `src/kirlian_terminal/artwork.py` | Local embedded/folder artwork, bounded decoding |
| `src/kirlian_terminal/cover.py` | Native, block, and disabled cover modes |
| `src/kirlian_terminal/graphics.py` | Capability selection and Kitty identifier/cleanup adapter |
| `src/kirlian_terminal/brand.py` | Terminal character sunburst and wordmark |
| `src/kirlian_terminal/appearance.py` | Validated preferences and curated themes |
| `src/kirlian_terminal/palette.py` | Bounded local artwork palette extraction and ribbon color blending |
| `src/kirlian_terminal/animations.py` | Versioned seeds, Braille/ASCII generators, independent animation clock |
| `src/kirlian_terminal/patterns.py` | The 100-pattern catalog's bounded geometry and character rendering |
| `src/kirlian_terminal/visuals.py` | Fixed-height filament widget and responsive progress line |
| `src/kirlian_terminal/playlists.py` | Saved playlists and ordered, duplicate-preserving entries |
| `src/kirlian_terminal/facts.py` | Optional Exa song facts, citation matching, credentials, local fact cache |
| `src/kirlian_terminal/app.py` | Browser views, search, onboarding, keyboard actions, worker messages |
| `src/kirlian_terminal/styles.tcss` | Terminal layout and initial colors |
| `tests/` | Generated audio, focus/navigation checks, and real-engine integration checks |

The active queue is the observed mpv playlist. Loading an album pauses the engine,
loads its ordered files, selects the requested index, then resumes. Explicit queue
operations share a lock so rapid actions cannot interleave a half-loaded album.
Append preserves duplicate entries. Saved playlists are separate from this queue;
see the playlist decision below. Queue restoration is not implemented.

SQLite connections are opened and closed within the operation that uses them.
Write-ahead logging lets the interface read committed batches during a scan.
Missing entries are marked unavailable after scanning, preserving their identity.
The current schema is the initial prototype; later schema changes must include
an upgrade path for populated libraries.

The mpv process ignores user configuration and auto-loaded scripts for predictable
behavior. External file references and the YouTube downloader are disabled.
Commands use JSON strings and subprocess argument lists, without shell interpolation.
Displayed metadata is plain text with terminal control characters removed.

## Deferred decisions

- License: decided — GPL-3.0-or-later, consistent with Mutagen. See `licensing.md`.
- Listening-position restoration: still deferred, including persistent queue-entry identity.
- Animation catalogue: the filament is accepted; additional families remain deferred.
- Visual reference: the owner supplied the album-view mock during the refinement pass.

## References

- [Textual workers](https://textual.textualize.io/guide/workers/)
- [Textual testing](https://textual.textualize.io/guide/testing/)
- [mpv JSON IPC and commands](https://mpv.io/manual/stable/#json-ipc)
- [Mutagen](https://mutagen.readthedocs.io/en/latest/)
- [uv projects](https://docs.astral.sh/uv/guides/projects/)

These references describe dependencies. The development record describes what has
actually been verified in this application.


## 2026-10-13: artwork and the first animation studies

The owner's album-view mock informed the masthead, quieter borders, album heading,
track-number column, local record pane, and full-width progress line. Short terminals
use a compact header; the context pane still disappears below 110 columns. The fact
card in the mock is not implemented and no mock facts are presented as real data.

Artwork is decoded in a background worker after a short navigation debounce. Each
request carries a revision; an older decode cannot replace the current selection.
The in-memory cache holds at most 24 albums and is cleared by a rescan. Embedded
front covers are preferred within ID3/FLAC tags; MP4 cover atoms and Ogg picture
blocks are also read. Folder covers follow embedded pictures. Input image bytes
are limited to 12 MiB, decoded images to 16 million pixels, and display copies to
384 × 384. No image is written back or cached on disk. These limits apply to image
decoding; Mutagen still parses the containing metadata file.

Pillow decodes the image; textual-image adapts it to the terminal. Its capability
query happens at import, before Textual owns input. The fallback trades image
resolution for portability. Native protocol behavior needs real-terminal checks,
including resize, clearing, and clipping. Dependency licenses are tracked separately.

Following a blank-image report with the context pane visible in Ghostty, `auto`
uses half-cell blocks when `TERM_PROGRAM=ghostty` or `TERM` contains `ghostty`.
This is a conservative compatibility workaround, not a claim that Ghostty lacks
Kitty graphics support. `--artwork native` and the `c` shortcut retain the option
to compare native rendering. The shortcut stores the preference in the existing
settings table. A launch flag overrides that preference for one process.

`NO_COLOR` always selects blocks: Textual's monochrome filter alters the RGB
identifier carried by Kitty Unicode placeholders, which can orphan otherwise
successfully transmitted images. Block rendering does not depend on those IDs.
Switching display clears the old renderer's image, reuses the decoded cover,
and leaves the current album and player untouched. Both renderers clear their
images at unmount. No new dependency or music-file write is involved.

The ASCII area is always 24 × 3 cells. A versioned family/seed pair determines a
variation. The animation clock accumulates active wall time rather than reading
audio position, so seeks do not jump the pattern. mpv's file-loaded event increments
a serial that distinguishes new plays, including repeat plays of the same path.
Pause, loading, idle, and disabled motion stop the animation timer. A subsequent
song selects a fresh seed. Saved seeds preserve the pattern, not the audio or phase.
The existing SQLite settings table stores the preference and seed list; no schema
migration is needed. Rendering remains bounded to 10 frames per second.


## 2026-10-13: accepted filament, appearance, and native image repair

This section supersedes the earlier Ghostty/block workaround and 24-column study.
The filament spans the available width, capped at 400 columns for bounded work,
and occupies three text rows. Each Braille cell packs a 2 × 4 dot grid; plain ASCII
is an alternate drawing. The seed and independent clock survive palette and
character changes. Still freezes time; off hides the drawing. Playback remains
owned by mpv. The progress line is independent of decoration.

Appearance is a validated JSON object in the existing settings table, with defaults
for unknown or malformed values. The old animation toggle is read only as a migration
fallback. The settings panel replaces the browser area and reuses the actual player
below it. Changes preview in memory; Keep persists, Cancel restores the snapshot.
It neither reconstructs the player nor issues playback commands. No schema migration.

Native Kitty placeholders encode an image ID in foreground RGB and combining
marks. Those bytes are protocol data: the adapter bypasses presentation filters
and the application preserves truecolor serialization for native graphics. Under
NO_COLOR, the cover pixels are grayscaled before transmission instead. Cleanup uses
`a=d,d=I,i=<id>`, targeting one image and its data; it must not clear other graphics.
This permits covers and the wordmark to coexist. The adapter depends on a small
private textual-image protocol helper; dependency upgrades must run its regression
checks. Sixel continues to use the upstream renderer.

The decoded cover limit is now 1024 pixels on each edge, downsampled with Lanczos;
source images are not artificially enlarged. The LRU holds 12 covers (roughly
36 MiB for full-sized RGB images), replacing the earlier 24-cover/384-pixel bounds.
Input byte and decoded pixel limits, background reads, and stale-result protection
remain. Native output is scaled to terminal cell pixels by the renderer.

Known partial implementations need explicit policy: automatic Warp rendering uses
blocks because the renderer documents missing Unicode placements despite a positive
graphics probe. An explicit native override remains available for changed terminal
versions. TERM=linux defaults to block artwork and ASCII ornament. These are fallback
policies, not claims that all named terminals have been visually verified.


## 2026-10-13: ribbon colors follow the playing album

The owner requested artwork-derived ASCII colors. The playing track's album owns
this palette, independently of the browsed record or image display mode. An
independent worker loads local artwork (reusing a cached cover when available),
reduces a copy to at most 64 × 64 pixels, and quantizes eight candidate colors.
It selects up to three substantial distinct colors, preferring chromatic colors
when present, lifts dark hues, and limits saturation for legibility. Neutral
covers remain neutral. The source image and music files are never modified.

The ribbon blends these colors across its width in short spans; its played section
uses brighter tints of the same colors. Color spans are cached until the palette
or width changes. Palette arrival never resets a seed, phase, or playback state.
The interface palette remains separate and supplies the missing-artwork fallback.
No additional dependencies, services, or model calls are involved.

A revision guard rejects late results after a track/album change. Sixty-four small
palette tuples are cached in memory; rescans invalidate them. Loading continues to
work when artwork is disabled or the context pane is hidden. Existing terminal
color mapping and NO_COLOR filters still apply to the filament.

## 2026-10-13: isolate blank native artwork

`--check-artwork` runs before mpv checks, library creation, and the Textual app. It
uses one generated picture to compare direct Kitty placement, the current player
placeholder encoder, and the half-cell fallback. It records bounded protocol
replies separately from a human visibility observation, then restores terminal
input modes and the normal screen, including on interruption. Reports contain
only terminal metadata, reply status, and the entered observation; no music or
local paths. This separates transport/placeholder failures from decoding and
Textual's lifecycle without changing the player's renderer based on guesswork.

The affected Ghostty session subsequently rejected direct PNG transmission with
`EINVAL: unsupported format`; the placeholder then returned `ENOENT: image not
found`. The Kitty adapter now transmits zlib-compressed RGBA (`f=32`, explicit
pixel width/height) in base64 chunks of at most 4096 characters. This bypasses the
rejected PNG format while preserving exact pixel values and alpha. Only the first
chunk carries image metadata; later chunks carry continuation and quiet flags.
Placement, placeholder IDs, and targeted cleanup remain unchanged. Resizing uses
Lanczos. The isolated diagnostic uses the same pixel transport.

Cover layout also uses a concrete bounding box computed from the decoded aspect
ratio, terminal cell dimensions, and available rows/columns. Upstream auto-height
measurement can read the image widget's previous width of zero, leaving a newly
shown image at zero height. Giving the child the calculated box removes that
circular measurement and keeps portrait/landscape covers within the caption budget.
The record pane owns resizing: its resize event has the actual pane geometry,
whereas the app-level event can still see dimensions from the previous layout.

The owner still reports blank native images after that change. Diagnostic version
2 therefore separates uncompressed RGB/RGBA, compressed RGBA, and PNG from the
player's placeholder path. Reference encodings live only in the diagnostic; the
production sender remains unchanged pending actual format responses. An optional
explicit report path stores JSON with bounded replies, entered visibility,
terminal/dependency versions, and hashes of the loaded diagnostic/renderer source.
It does not inspect the library or persist terminal preferences. Asking the
terminal for its own version avoids treating installed bundle metadata as proof
of which process is responding.

## 2026-10-13: distinguish embedded engines from their host environment

The saved version-2 report identifies `libghostty`, accepts all raw formats and
placeholder placement, rejects PNG, and records only the block sample visible.
Its source fingerprints match this checkout. Ghostty's library defaults to that
version string when its host supplies no identity callback; the standalone app
answers with `ghostty` and its version. Consequently the environment variable
alone was an insufficient basis for diagnosing the session as the standalone app.

Added a cached, bounded live version query before Textual starts, only when the
initial capability probe selected the Kitty protocol. Generic `libghostty` gets
block covers and a text logo in automatic mode because the host's renderer is
unidentified. Explicit native mode still bypasses this conservative selection;
identified Ghostty/Kitty and missing replies retain the existing capability path.
This is a compatibility choice, not a claim that every libghostty host lacks
image support. The shared reply reader has a total deadline/byte cap and restores
terminal input mode. Diagnostics use the same parser and explain this identity.

## 2026-10-13: terminal-native identity and multiplexer boundaries

The owner replaced the graphic-header direction with a terminal-native mark.
`Brand` is now a single text widget: original letter strokes and eight open-center
rays are sampled into two rows of Braille cells. The ASCII variant pairs a
punctuation emblem with ordinary monospace lettering. Short windows and the Simple preference use a
one-line mark. These are ordinary terminal cells with normal color filtering;
no Pillow, custom font, image upload, placement, or image cleanup is involved.
Existing `logo=auto` / `logo=text` preferences retain their values and now select
Drawn / Simple. The earlier font-derived assets are removed from the package.

Herdr is the previously unidentified embedded host, not Codex. The installed
0.8.2 client and server expose opt-in Kitty graphics under `[experimental]`.
A generic `libghostty` reply still selects blocks conservatively: protocol ACKs
alone do not prove that a host renders placements. After configuring the host,
`--artwork native` permits explicit verification without changing fallback policy.

The pinned textual-image helper already wraps image chunks, placements, cleanup,
and terminal queries in tmux DCS envelopes when `TMUX` is set. We reuse that path;
Herdr's own graphics implementation does not require pretending it is tmux.
Nested multiplexers and multiple clients require separate real-host testing.
The diagnostic records only presence/absence of Herdr socket and pane environment
keys, never their paths or identifiers.

## 2026-10-13: tighter browsing and playback hierarchy

The collection heading and count now share a row. Only an open album needs a
breadcrumb; the root collection does not repeat “Your library”. Library rows
retain the application surface even while focused, overriding Textual's default
focus tint; the selected row remains accented. The sidebar uses accent text until
focused, so it does not compete with the selected record. Duration cells align
right and table labels reflect the collection being viewed.

One footer pairs contextual Enter/Space hints with pattern, help, quit, and
volume. Search and personalization stay in the masthead; the other actions remain
in Help and keep their bindings. The full-width three-row filament is unchanged.
The ordinary player is one row shorter and no permanent readiness message is
shown. Status still retains errors and useful operation results until explicitly
cleared. An empty record note no longer draws a divider. No native-image transport
or sizing changes are part of this layout pass.

## 2026-10-13: cover latency and bounded repaint work

The Kitty widget now retains up to 12 renderables, keyed by source image identity,
styled size, actual bounds, and terminal cell dimensions. Cache entries retain
their source object so recycled Python IDs cannot alias another image. Repaints
and revisiting a cached cover reuse the terminal image and virtual placement.
A new size needs a new prepared renderable; eviction, explicit clearing, switching
to blocks, and unmounting delete only owned image IDs. Other applications' graphics
remain untouched. Sixel and block rendering retain their existing paths.

Copying pixels, Lanczos resizing, RGBA conversion, compression, and base64 encoding
for the Kitty widget run in a cancellable background worker. A request key rejects
late results after selection or size changes. Only accepted results can transmit
image data. The isolated diagnostic retains synchronous preparation because it
does not run the interactive UI. Chunk format, compression, image quality,
placeholder colors, and multiplexer wrapping are unchanged. Protocol writes still
use the existing output helper; slow terminal transport can add latency.

The decoded-cover cache still holds 12 entries. NO_COLOR also retains up to 12
grayscale display images, allowing native cache reuse without recreating an image
object on every visit. These are additional bounded memory costs, including the
renderables' pixel copies and encoded payloads; the earlier 36 MiB estimate covers
only the decoded RGB cache, not total process or terminal memory. No disk cache or
media-file modification is introduced.

Cached covers replace the current image directly. On a cache miss, the old cover
is hidden while loading without destroying reusable terminal data. A 40 ms debounce
replaces the earlier 120 ms delay; stale decode results still cannot overwrite the
current selection. Changing tabs to a view without artwork explicitly clears it.

Table resize events now resize columns instead of rebuilding library rows. Column
layout skips unchanged widths/view labels. `LibraryTable.refresh_columns` clears
DataTable's rendered-cell caches and recomputes its virtual scroll dimensions
without changing rows. These two upstream private methods need resize regression
coverage when upgrading Textual; a plain layout refresh leaves stale scroll width.
Fixed-size player labels update only
when their displayed content changes, with no layout pass. The animation timer
owns moving frames at 10 Hz; position events no longer add duplicate frames. The
three-row ribbon updates without requesting a screen layout, and the progress line
repaints only when its visible cell changes. Playback transitions, pause, resize,
appearance preview, and palette changes still draw the required new state.

## 2026-10-14: a versioned catalog of 100 ribbon patterns

The owner confirmed improved responsiveness and requested about 100 permutations.
Added ten geometric families and ten named profiles per family. Version-2 pattern
identifiers store the family and profile index; geometry uses a fixed per-recipe
seed. Names and recipes form part of the saved-pattern contract. A future visual
redesign must use a new version rather than reinterpret a saved v2 identifier.
Version-1 rendering is preserved separately, including the legacy ASCII projection.

`PatternDeck` maintains a session-only pool. The initial drawing counts as the
first entry; new songs and explicit shuffles share the remaining pool. Selection
prefers a different family when possible, avoids immediate repeats, and refills
after exhausting the catalog. Manual recall remains independent and can revisit
favorites; a recalled final pool entry cannot strand the next shuffle. The existing
SQLite string list stores both versions, with no schema or preference migration.

The v2 renderer writes into three rows of Braille bit masks directly. Its ASCII
projection preserves separate row-level strands rather than averaging all vertical
positions into one row. Geometry depends only on the recipe, elapsed animation
time, and bounded width. Ring count is capped and ellipse sampling visits only
visible columns, avoiding disproportionate work at 400 columns. No simulation
history, image buffers, per-pattern timers, network, or media IO is introduced.
The existing clock, palette bands, progress highlight, motion controls, and
layout-free 10 Hz drawing path remain in charge of playback presentation.

## 2026-10-14: visible preference state and reliable saves

The settings form remains a reversible preview. Save reads the current Select
values directly: their asynchronous change messages may not yet have updated the
preview model. Preview changes also read the whole form, and programmatic opening
and resetting suppress redundant Select messages. This avoids saving stale values
or replaying an old field event over a more recent selection.

The existing SQLite write runs in a background thread. While it commits, the form
is disabled and says it is saving; success closes the form and confirms persistence.
A database or filesystem error keeps the preview, restores the controls, and allows
retry or cancel. Cancel before saving still only restores the opening snapshot.
The transaction does not change the queue, music files, or saved pattern collection.

An accent sample, unsaved-state label, explicit Save changes action, and Ctrl+S
make the preview/save distinction visible. Contextual text explains album-derived
ribbon colors, paused motion, the compact header, and NO_COLOR. These explain
existing rendering rules rather than overriding the terminal or playback state.

## 2026-10-26: saved playlists

The owner brought saved playlists forward. Two tables in the existing database
hold them: `playlists(id, name)` and `playlist_entries(id, playlist_id, position,
path)`. Each entry has its own id, so a song added twice stays two rows and one
copy can be removed or moved without touching the other. Entries reference the
file path, the same identity the library uses; a path that disappears from the
library is shown as unavailable rather than deleted. Tables are created with
`IF NOT EXISTS`, so existing libraries need no migration.

Moves swap neighbouring positions inside one `BEGIN IMMEDIATE` transaction, and
appends compute the next position inside the same transaction, so rapid key
presses cannot reorder from a stale read. All playlist reads and writes run in
worker threads; the UI keeps the current list and open playlist's entries in
memory for drawing.

Playing a playlist loads its available entries into mpv in saved order and
starts at the chosen entry; missing files are skipped, not dropped. The active
queue is still mpv's playlist, so playing a saved playlist replaces the queue
exactly like playing an album. Playlists appear as one sidebar view rather than
one sidebar row each, to keep the navigation list fixed.

## 2026-10-26: optional song facts through Exa

The owner chose Exa as the single provider and supplied a mock for the
"Behind the record" card. The player calls `POST https://api.exa.ai/answer` with
a plain-language question and an `outputSchema` asking for up to three facts, each
with a headline, body, and the URL of its source. Exa's response also lists the
pages it actually retrieved (`citations`). A fact is kept only when its URL matches
one of those citations, ignoring scheme, `www.`, and a trailing slash; the card
shows that citation's title, year, and URL. A model-written URL alone is never
shown. Headlines, bodies, and titles are clipped and stripped of terminal controls.

Only title, artist, album, and year are sent. The request uses `urllib` from the
standard library with a 25-second timeout, in a worker thread. It starts two
seconds after mpv reports a new song; a revision counter discards an answer that
arrives after the song changed, though the answer is still cached. Answers,
including empty ones, are stored in a `facts` table keyed by casefolded
artist/album/title, so each song is requested once overall, not once per launch.
Failed requests are not cached but are not retried in the same session.

Facts are explicitly opt-in: the `facts` setting must be `on`, which only the
setup dialog (`i`) sets. An `EXA_API_KEY` in the environment supplies a key but
does not turn facts on. Keys come from the environment, then a session-only value,
then the OS credential store through `keyring` (MIT). If no credential store is
available, the key is held for the session only. The key never enters SQLite,
logs, or the repository. Turning facts off forgets the stored key.

The card sits under the album details in the record pane and follows the
*playing* song. It is shown only while the pane shows that song's album, so the
fact never appears beside a different record. While it is visible the record note
hides and the cover is sized to leave room for it.
