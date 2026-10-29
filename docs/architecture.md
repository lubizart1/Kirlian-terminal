# Architecture and decisions

## 2026-10-13: an independent local application

The supplied handoff selects Python 3.12+, Textual, mpv JSON IPC, Mutagen, SQLite,
platformdirs, and uv. Keep these choices unless a documented owner decision changes
them. The project is GPL-3.0-or-later, consistent with Mutagen's GPL-2.0-or-later
license (see `licensing.md`). The application does not import or call
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
| `src/kirlian_terminal/patterns.py` | The 180-pattern catalog's bounded geometry and character rendering |
| `src/kirlian_terminal/visuals.py` | Fixed-height filament widget and responsive progress line |
| `src/kirlian_terminal/playlists.py` | Saved playlists and ordered, duplicate-preserving entries |
| `src/kirlian_terminal/facts.py` | Song-facts providers, response readers, source matching, credentials, fact cache |
| `src/kirlian_terminal/i18n.py` | Interface language: locale detection, catalogs, `_`/`n_` lookup with English fallback |
| `src/kirlian_terminal/locales/` | One JSON catalog per language, English source to translation |
| `src/kirlian_terminal/facts_check.py` | `--check-facts`: one live request per provider, explained |
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
- Animation catalogue: 180 patterns in 18 families; see `patterns.md`.
- Visual reference: the owner supplied the album-view mock during the refinement pass.

## References

- [Textual workers](https://textual.textualize.io/guide/workers/)
- [Textual testing](https://textual.textualize.io/guide/testing/)
- [mpv JSON IPC and commands](https://mpv.io/manual/stable/#json-ipc)
- [Mutagen](https://mutagen.readthedocs.io/en/latest/)
- [uv projects](https://docs.astral.sh/uv/guides/projects/)

These references describe dependencies. [Testing](testing.md) describes what has
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

## 2026-10-26: optional song facts (first provider: Exa)

The owner chose Exa as the single provider and supplied a mock for the
"Behind the record" card. The player calls `POST https://api.exa.ai/answer` with
a plain-language question and an `outputSchema` asking for up to three facts, each
with a headline, body, and the URL of its source. Exa's response also lists the
pages it actually retrieved (`citations`). A fact is kept only when its URL matches
one of those citations, ignoring scheme, `www.`, and a trailing slash; the card
shows that citation's title, year, and URL. A model-written URL alone is never
shown. Headlines, bodies, and titles are clipped and stripped of terminal controls.

Only title, artist, album, year, and language are sent. The request uses `urllib` from the
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

## 2026-10-26: listener-chosen facts provider

The owner asked not to force Exa. The setup dialog now offers Exa, OpenAI,
Anthropic, Perplexity, and Parallel; the choice is stored as `facts_provider`
(default `exa`, so the earlier setup keeps working). `facts.py` holds one table of
`Provider` records: endpoint, auth header style, default model, a request-body
builder, and a response reader. There is no plugin mechanism; adding a provider
means one table entry and, at most, one reader.

All providers are asked the same question and asked to return the same JSON
(`facts[]` with headline, body, `source_url`). Each reader returns that answer
plus the pages the provider's search actually retrieved, and one shared check
keeps only facts whose URL matches a retrieved page. This keeps the "no
model-written URL alone" rule identical across providers:

| Provider | Call (as documented 2026-10) | Structured output | Retrieved pages read from |
| --- | --- | --- | --- |
| Exa | `POST /answer` | `outputSchema` | `citations` |
| OpenAI | `POST /v1/responses`, `gpt-5.4-mini`, `web_search` tool | strict `text.format` | `url_citation` annotations, `web_search_call.action.sources` (via `include`) |
| Parallel | `POST /v1/responses`, model `parallel`, `reasoning.effort: low` | `text.format` | `url_citation` annotations, `open_page` actions |
| Perplexity | `POST /v1/agent`, `effort: fast` | `response_format` | `search_results` output item |
| Anthropic | `POST /v1/messages`, `claude-sonnet-5-5` (was `claude-haiku-4-5`), `web_search_20250305` (5 uses) | prompt only; JSON taken from the final text block | `web_search_tool_result` blocks and text citations |

Perplexity's Sonar chat-completions API was retired on 2026-09-27; the Agent API
is its documented replacement. OpenAI, Parallel, and Perplexity share one reader
because their responses use the OpenAI Responses `output[]` shape. The timeout
rose to 60 seconds because Perplexity documents a 10-30 second delay the first
time a schema is used and Parallel's research takes 5-10 seconds at low effort.
Default models will age; the settings screen sets a model for OpenAI and
Anthropic (this replaced a short-lived `KIRLIAN_FACTS_MODEL` variable). Gemini is not offered because its grounding returns redirect
URLs, not the source pages the shared check needs.

Keys are stored per provider (keyring user = provider id, environment variable
per provider). Switching providers keeps the other keys; turning facts off
removes all of them. Cached facts are keyed by song, not provider, so switching
does not pay for songs already answered.

## 2026-10-26: title rhythm as the facts loading state

The owner asked for a loading indicator that is not a shimmer, spinner, or
"thinking" text, prompted by the Oblique Strategy "convert a melodic element into
a rhythmic element". The melodic element is the playing song's title: `rhythm()`
in `visuals.py` reads it as a step pattern (vowel groups approximate syllables;
first syllable of each word accented; each digit a hit; a rest between words;
at most 16 steps), and `TitleRhythm` walks a playhead across it every 0.15 s, with
the previous hit lingering one step. It uses the interface accent and the
existing character choice (`● • ·` or `X x .`).

It appears only while a provider request is in flight (not during the two-second
skip delay or for cached songs), in place of the fact text and source line. The
timer exists only in that state: it is not started under Still/Off motion or when
the side pane is hidden, and it stops when the answer or an error arrives, the
song changes, or facts are turned off. Turning facts off now also advances the
fact revision, so an answer still in flight is discarded.

## 2026-10-26: `--check-facts`

Provider response shapes are the untested part of song facts, so a live check
mirrors `--check-artwork`: it runs before mpv and the UI, makes one request with
the saved/exported key (or one typed with `getpass`, never stored), and reports
timing, retrieved pages, and per-fact pass/fail against the same source check
the player uses. `fetch_payload()` was split from `request_facts()` for this;
`FactsError.detail` carries the provider's own error body (clipped, controls
stripped) for the check, while the player still shows only the short message.
The optional JSON report stores the provider response but never the key.

## 2026-10-26: annotations, fallbacks, and the settings screen

Live comparison by the owner: Anthropic's answers were accurate but obvious
(engineers, studios, mixing credits). The owner asked for Genius-annotation-style
notes that infer things about the song from context.

**Question.** The prompt now asks for annotations about meaning, lyric references,
circumstances, the song's place in the artist's work, and audible choices, and
discourages credit and studio lists. Each note has a `kind`: `story` (a source
states it) or `reading` (an interpretation connecting what sources say). This
keeps the source rule intact: interpretation is allowed, but a reading still
needs a retrieved page supporting its basis, and the card labels it ("A reading,
drawing on …") so it is never presented as fact. An unknown kind is shown as a
story; the schema and prompt offer only the two kinds.
`PROMPT_VERSION` is part of the cache key, so earlier answers are asked again and
old rows are deleted on open. The Anthropic default moved to `claude-sonnet-5-5`
with five searches and 2048 output tokens; the timeout is 90 s.

**Per-provider cache.** Facts were cached per song only, so after switching
providers the old provider's answer kept appearing and the new provider was
never asked, which made comparison impossible. The cache key is now
`v<version>/<provider>/<song>`, and the card says which provider answered.

**Order and fallbacks.** `FactsConfig` (settings key `facts_config`) holds the
ordered providers in use and per-provider model overrides; it migrates the
single `facts_provider` setting. Providers are tried in order. A provider's
cached answer, including "nothing found", ends the search; a failure (HTTP error,
quota, timeout, unreadable reply) or a missing key moves to the next. Failures
are not retried within a session until the settings screen closes. Fallback on
"nothing found" was rejected: it would bill every provider for obscure songs.

**Settings screen.** `i` opens a modal table of all providers (fixed row order,
with the order number, model, and where the key comes from). Keys are added or
rotated in a separate password dialog (keychain or session), removed with `d`,
and never displayed. Environment keys are shown as such and cannot be removed
from inside the app. Turning notes off keeps keys; removing keys is explicit.
The earlier single-provider dialog lost pasted keys when the provider dropdown
still had focus; key entry now always starts in a focused input.

**Source labels.** Labels add the site (`Air · uncut.co.uk`). Anthropic's
`page_age` values like "7216 days ago" measure from a page's last update, so
they are dropped rather than turned into a misleading year.

## 2026-10-28: settings screen readability

Owner feedback on the first settings screen: it was unclear whether `m` changed
anything and why, and reordering fallbacks was hard because rows stayed in a
fixed order while only a number column changed. Rows are now sorted by role
(Primary, Fallback N, Not used); moving a provider moves its row and the
selection follows it by provider id, not row index. `1`-`5` place a provider
directly; Shift+arrows move it. A detail line explains the selected provider's
role in words ("Fallback: asked only if Perplexity fails") and which model
writes its notes, and the action line lists only actions that apply (no `m` for
providers without a model choice, no `d` without a saved key). The model column
is "Writes notes with". The model picker is a list of suggested models, each with
what to expect, plus "Another model…" for a typed name; it states that the model
affects song notes only. Choosing the default removes the override.

## 2026-10-28: type mark replaces the drawn wordmark

The owner found the header wonky: two rows of Braille dots tracing a serif
wordmark read as noisy at that size. Choosing between the real wordmark image
(sharp only with terminal graphics, earlier blank in some hosts, and needing
font/brand rights confirmed) and a type mark, the owner chose the type mark from
the album-view mock: `✺  kirlian`, glyph in ink and name in bold ink, one line at
every size. `✺` (U+273A) replaces `✳` (U+2733) here and on the fact card because
U+2733 has an emoji form that macOS can substitute with a color emoji when the
terminal font lacks it. ASCII characters use `*`.

The drawn Braille letter paths, the Drawn/Simple "Header" preference, the
"needs 30 rows" note, and the two-row masthead are removed; the masthead is three
rows (two in compact layouts). An `appearance` value saved with the old `logo`
key is ignored on load, since unknown keys were already dropped.

## 2026-10-28: interface languages

The owner asked for multilingual support with common languages by default. The
interface ships in English plus Spanish, French, German, Italian, Brazilian
Portuguese, Japanese, Korean, and Simplified Chinese.

No gettext toolchain or new dependency: `i18n.py` loads one JSON catalog per
language, keyed by the English source string, so code stays readable and a
missing entry falls back to English instead of breaking. Placeholders use named
`str.format` fields; `n_` covers count-dependent wording with a per-language
rule (one/other for most; French and Portuguese treat 0 as one; Japanese, Korean,
and Chinese have one form). Sentences are translated whole; styled text is built by
translating the full sentence and splitting it at the placeholder. Tags, file
names, provider text, model and provider names are always inserted values.

`scripts/i18n_catalog.py` extracts literal arguments of `_`, `n_`, and `N_` with
`ast` and checks every catalog for missing and stale keys and placeholder
mismatches; tests run it for each language and format every string, so a broken
placeholder fails CI rather than raising in the UI.

The language resolves at launch: a saved choice, else `LC_ALL`/`LC_MESSAGES`/`LANG`
(`pt_*` maps to pt-BR; `zh_CN`/`zh_SG` to Simplified Chinese; Traditional Chinese
and unlisted languages to English). Switching was first deferred to the next launch
(superseded below). Song notes are asked
for in the active language and cached per language (English keeps its earlier
keys). The CLI, `--check-facts` output, Textual binding descriptions, and key
names remain English. Translations were drafted by AI agents per language and
need native review; [testing](testing.md#not-yet-verified) lists the flagged judgment calls.

## 2026-10-28: switch language without relaunching

The owner saved a new language and saw no change, since it waited for the next
launch. Saving a different language now calls `apply_language()`: it sets the
catalog, recomposes the screen (widgets hold text built in the old language), and
reruns `prepare_screen()`, the same setup `on_mount` uses, minus `boot()`. Playback
is unaffected because mpv, the queue, the library, the current view, and caches
live on the app, not in widgets; the view, selected row, sidebar section, player
labels, ribbon palette, and cover (from the in-memory cache) are redrawn. The
playing song's notes are requested again in the new language. Table columns are
added before the appearance is applied, because applying it can redraw rows.
The time column now widens to its translated header ("DURACIÓN"), and the
sidebar is two columns wider for "File d'attente".

## 2026-10-28: dropped connections

`fetch_payload` resends once when the connection drops before any reply
(`ConnectionError`, `http.client.HTTPException`); HTTP errors and timeouts are not
resent. `FactsError.transient` marks connection failures: those are removed from
the session's asked set so the song is tried again on its next play, while
rejected keys and quota errors stay blocked. A provider with a key that is not in
the order is suggested in the status line, never used without being chosen.

## 2026-10-28: the amp and a ribbon that hears the music

The owner asked for more from the bottom visuals and a Winamp-like amp toggle.
Both use mpv's own audio filters, so playback stays in the owned mpv process and
no audio is decoded by the app.

**Levels.** mpv starts with `--af=@meter:lavfi=[astats…,aspectralstats…]`:
per-frame RMS and peak per channel, spectral centroid, and spectral flux, read
through the `af-metadata/meter` property. Both filters pass audio through
unchanged. A worker polls about 20 times a second, only while a song plays and
the ribbon moves or the amp is open. `Levels` maps RMS from -40 to -6 dB to an
energy of 0 to 1 (sampled real tracks sat between -25 and -8 dB) and the centroid
from 200 Hz to 8 kHz to brightness.

**Ribbon.** `Reaction` smooths energy and brightness. Energy sets the animation
clock's rate (0.45 to 1.85 times, changed without jumping the frame); brightness
lifts the ribbon toward white by up to 22%; flux above 2.2 times its running
average while the music is loud starts a spark that lights nearby ribbon cells
and fades in 0.4 s. On two sampled tracks this gave about 1.5 sparks per second.
This supersedes the specification's "decorative, does not visualize audio":
the motion is now driven by measurements, while the shapes stay the catalog's.

**Equalizer.** `AmpSettings` holds ten band gains, preamp, balance, preset,
ReplayGain mode, and whether the amp is open (settings key `amp`). When on, mpv's
filter list is `@eq:lavfi=[equalizer@b0…b9, volume@pre, stereotools@bal]`
followed by the meter, so meters show what plays. Turning it on or off rebuilds
the list with `af set`; when off, the `@eq` stage is absent, not neutral. Moving a
slider uses `af-command eq <command> <value> <filter>` so the running audio
changes without a rebuild. Because mpv recreates filters from the installed list
when audio reinitializes, the list is reinstalled while the next song loads if it
differs from what was tuned. ReplayGain is mpv's `replaygain` property. Codec,
bitrate, sample rate, and channel count come from observed mpv properties.

**Panel.** `AmpPanel` draws meters (peak hold one second, then 20 dB per second),
a balance slider, ReplayGain modes, and Winamp-style vertical sliders for the
preamp and ten bands; below 36 rows the sliders become one row of block bars. It
owns arrow keys and Escape while focused (the app's priority arrow bindings are
disabled for it); the app owns the settings and talks to mpv. Saving waits 0.3 s
so a held key writes once. Strings are translated in all nine languages.

## 2026-10-28: real frequency bars, a display-only amp, and the Sound screen

The owner found the first amp hard to use (a hidden slider grid that captured the
arrow keys) and asked for real per-frequency bars, then for pitch and speed.

**Bars.** mpv's metadata only reports filters on the audio path, so the bands
ride along as audio: the meter graph forces stereo, splits off a mono copy, runs
it through twenty half-octave `bandpass` filters (40 Hz to 16 kHz, log-spaced),
`amerge`s the bands as extra channels next to the stereo signal, measures every
channel with `astats`, then `pan=stereo|c0=c0|c1=c1` keeps only the two real
channels. Frame metadata survives `pan`, so `af-metadata/meter` carries channels
1-2 (levels) and 3-22 (bands); `aspectralstats` runs after `pan`. Checked against
two sine tones (100 Hz and 4 kHz bars peaked) and a real AAC track. The cost is
twenty biquads per sample. Side effect: output is always stereo (mono files play
on both sides; surround is folded), which is what most listening setups get anyway.

**Amp.** The panel no longer takes focus or keys; it draws bars (eighth-block
heights, -60 to -10 dB, instant rise and 1.6 per second fall, caps that hang 0.4 s),
meters, and a status line. CLIP is shown only when the equalizer is on, since
mastered music routinely peaks at full scale.

**Sound screen.** A modal list with one row per control: the same up/down,
left/right model as the other settings screens, and a sentence for the selected
row (each band has a plain description of what it shapes). It drives the same
app methods as before, so live tuning and filter reinstalls are unchanged.

**Speed and pitch.** mpv's `speed`, `pitch`, and `audio-pitch-correction`
properties: speed keeps the key (scaletempo2), pitch shifts by 2^(n/12) keeping
the speed, and Tape turns pitch correction off so pitch follows speed. Verified by
rendering output with `--ao=pcm`: speed 1.5 shortened 4.0 s to 2.67 s at the same
centroid; pitch +5 semitones raised a 440 Hz centroid to about 604 Hz; speed 1.5
without correction raised it to about 691 Hz. These are session-only (`Tempo`) so
a song never starts slowed by surprise. mpv applies them after the app's filters,
so bars show the pre-speed spectrum.

## 2026-10-28: rebuilding guard

A language switch recomposes the screen while mpv keeps reporting. `rebuilding`
marks that window: handlers update app state only (`display_state`, caches) and
skip widget queries; `apply_language` redraws everything from state after
`prepare_screen`. New code that touches widgets from player events, workers, or
timers must respect this flag.

## 2026-10-28: pattern reveal, music per family, depth

**Sound in patterns.** `patterns.render(..., sound)` takes a `Sound` (bass, mid,
treble, energy, hit, pulse, each smoothed by `Reaction` from the twenty bands and
onsets). Each family scales one parameter by it; with `sound=None` the code path
is the original one, so saved patterns keep their exact drawings (verified by
hashing all 100 patterns at several times and widths before and after). `pulse`
glides toward a count of hits, so ripple rings travel on kicks without jumping.

**Depth.** `DotField` records which dots are main strokes; `Frame.depth` marks
cells holding only fine detail, which the ribbon draws mixed 45% toward the
surface color. Colors are computed per column (with sparks and brightness lift)
once per frame and reused for all three rows; equal styles are merged into runs.

**Reveal.** A pattern change keeps the outgoing variation and its frozen time.
For 0.7 s each Braille dot switches from old to new at its own fixed
pseudo-random moment (`scatter`), so the change looks grainy rather than wiped.
The new label's letters arrive over 0.25 s, hold to 1.2 s, and scatter by 1.8 s.
The timer runs for the reveal even when paused after `x`; pausing, Still, and
Off cancel a reveal in progress, and a song that loads paused shows none.
Measured cost of a reveal frame: 2.9 ms at 156 columns, 7.3 ms at 400.

## 2026-10-28: eight more families

Aurora, rain, loops, heartbeat, comets, lattice, petals, and dunes bring the
catalog to 180. They are appended to `FAMILIES`, so every earlier family keeps
its index, seed, and saved `v2` code (checked by comparing all 100 earlier
patterns before and after). Each new family marks main and fine strokes for
depth and answers one part of the music, like the original ten. Labels stay
English proper names, as before.

## 2026-10-28: pre-launch hardening

- **Untrusted input never reaches a traceback.** Textual prints worker tracebacks
  with local variables, and the facts workers hold the API key. Provider text that
  broke URL parsing or the JSON parser, or a locked fact cache, used to raise there.
  Now malformed URLs simply fail to match, unreadable answers become `FactsError`,
  the cache is best effort, and the two workers holding a key run with
  `exit_on_error=False` as a last guard.
- **Cover art decodes with plain image formats only** (JPEG, PNG, WebP, GIF, BMP).
  Pillow's EPS reader would hand PostScript from a tag or `cover.jpg` to Ghostscript.
- **Song notes send tag text only.** Tracks record whether title and album came
  from tags (`tracks.tagged`); filename and folder stand-ins are never sent. Older
  libraries get the column as "not tagged" until the launch rescan fills it in.
- **Answers are cached under the language they were asked in**, so switching
  language mid-request cannot file English notes under French.
- **Ordered amp updates.** Each amp change is a diff applied over several mpv
  commands; an `asyncio.Lock` applies them strictly in order, so a slow earlier
  change cannot land after a later one.
- **A playlist load is kept only if that playlist is still open.**
- **CI** (`checks.yml`): lint, format, and translation coverage once; tests with
  real mpv on Ubuntu and macOS for Python 3.12–3.14; a build that installs and
  starts the wheel. `release.yml` turns a `v*` tag matching the package version into
  a draft GitHub release only, so publishing stays a deliberate step. Dependabot
  proposes monthly updates.
