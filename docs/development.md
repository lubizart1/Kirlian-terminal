# Development record

## 2026-10-13: project start

The repository contained only its Git directory, with no commits or remote.
The owner supplied an implementation handoff and requested documentation throughout
development for a future public repository.

The current scope is Milestone 1 only: installable project, folder onboarding,
background indexing, album/track browsing, search, queue, and core keyboard control.
The product specification preserves the supplied handoff. Documentation, package
setup, and public-repository ignore rules are now in place.

The initial application is implemented for the Milestone 1 review. It has a Python
package and `kirlian` entry point, folder onboarding, background scans, SQLite
persistence, album/artist/song views, search, an mpv-owned queue, append/jump
actions, keyboard playback controls, and readable error states. The context pane
hides in narrow terminals. There are no provider integrations or API calls.

The README documents installation and behavior. The architecture notes record
ownership and data boundaries. `AGENTS.md` and `CONTRIBUTING.md` require future
changes to update these records alongside code. The supplied handoff is preserved
in `specification.md`; `testing.md` provides the manual listening procedure.

## Verification environment

- macOS 26.5.1, Apple silicon arm64.
- Python 3.13.12 and a separate Python 3.12.12 environment.
- Textual 8.2.8, Mutagen 1.48.1, platformdirs 4.13.0, pinned in `uv.lock`.
- mpv 0.41.0, using FFmpeg 9.0.2.
- mpv was installed through Homebrew for this check. Homebrew also installed or
  upgraded its dependencies, including FFmpeg.

## Playback and interface checks

- Indexed the owner's supplied local collection: 65 audio files, 51 album groups,
  MP3 and M4A, with no unreadable-file errors.
- Verified all 67 original files in the folder, including non-audio files, retained
  their SHA-256 hashes after indexing and playback.
- Used real files and a real mpv process to check pause, seek, volume, append,
  queue jump, and a transition between two tracks without replacing the process.
  The transition check sought near a track's end; it was not a full-album listen.
- Exercised the Textual interface with real mpv using a null audio output. Playing
  from the browser, pause/resume, typing search without affecting playback, Escape,
  resizing, and quitting passed. Rendered views were inspected at 80 × 24 and
  120 × 36. The current environment requests `NO_COLOR`; a separate process also
  checked the initial aubergine/bone palette with that override absent.
- A separate real-file check used the normal CoreAudio output for approximately
  three seconds at 8% player volume, with elapsed playback and no engine error.
  This is an output-path smoke check, not a human audio-quality judgment.
- Launched the CLI in an 80 × 24 Codex pseudo-terminal, indexed the folder, and
  quit cleanly. No named terminal application is certified by this check.
- The computer-use tool denied access to Terminal.app. Its native UI therefore
  remains untested; no workaround was used to control that application.

## Final automated and installation results

| Check | Result |
| --- | --- |
| `uv run pytest -q` on Python 3.13.12 | 23 passed, none skipped |
| `uv run --isolated --python 3.12 --locked pytest -q` | 23 passed, none skipped |
| `uv run ruff check .` | Passed |
| `uv run ruff format --check .` | Passed |
| `uv build` | Source archive and wheel built successfully |
| Clean source extraction, `uv sync --locked`, then `uv run kirlian --version` | Installed successfully; version `0.1.0a1` |
| Wheel installation in a fresh Python 3.12 environment | Installed successfully; command entry point works |
| Public package inspection | Runtime modules and terminal stylesheet present; local test data and music excluded |
| Relative documentation links | No missing targets |

The tests include real mpv decoding of generated MP3, FLAC, M4A, raw AAC, Ogg
Vorbis, Opus, and WAV files, plus queue and process-lifecycle checks. All automated
audio checks use null output. The separate CoreAudio check is described above.

The initial failures and subsequent corrections are retained below so a passing
final run does not erase what was learned during implementation.

## Issues found and addressed

- A newly installed mpv initially exceeded the startup timeout while its own
  version command was also delayed. After that command completed, playback
  succeeded. Startup now displays progress, allows 15 seconds, and gives a
  restart instruction on timeout. The cause of the initial delay is unconfirmed.
- On terminal resize, reading the old application size left the context pane
  hidden. Layout now uses the resize event's dimensions.
- mpv reports queue position and path before a file is necessarily ready to seek.
  The interface now observes file-loading events, shows a loading state, and
  rejects an early seek with an understandable message. Tests wait for actual
  playback readiness rather than assuming property events form an atomic snapshot.
- A scan completion could return after UI shutdown had started. Late updates now
  check application lifetime before rendering, and the scan is marked complete
  after the library refresh finishes.
- The installed FFmpeg build lacks the optional libvorbis encoder. Generated Ogg
  fixtures use FFmpeg's native Vorbis encoder instead; this changes only fixture
  generation, not the application's playback engine.

## Review boundary and open checks

- The owner must select a repository license before public release. *(Resolved
  2026-10-26: GPL-3.0-or-later.)*
- The referenced visual mockup was absent at this checkpoint; supplied in the refinement below.
- A complete real-album listening pass, including audible gap checks, remains
  required. The supplied collection contains partial albums, so indexing it does
  not establish complete-album coverage.
- Linux and native terminal-app verification remain outstanding. The GitHub
  workflow is configured, but has not been run on a remote repository.
- At this checkpoint, saved playlists, restoration, artwork, animations, and facts were deferred. Do not infer their implementation from the product specification.
- This is a local prototype, not a published release. The repository still has no
  remote or initial commit. The owner subsequently reviewed the interface and requested the refinement below.


## 2026-10-13: cover artwork and ASCII refinement

The owner supplied an album-view mock and requested visible cover art and an
animated ASCII play bar. This explicitly brought those parts forward while saved
playlists and optional sourced facts remain deferred. The supplied implementation
handoff in `specification.md` remains unchanged as a record of the original brief.

Implemented local embedded/folder cover loading, a bounded in-memory image cache,
stale-result protection, two seeded procedural families (filaments and ripples),
pause/resume without phase jumps, a persistent motion toggle, shuffle, and saved
seed recall. Refined the masthead, album hierarchy, track columns, context panel,
progress line, and small-terminal spacing against the mock.

The first screenshot review exposed excessive header space at 80 × 24 and track
columns retaining their previous widths after resize. The compact layout and
Table resize handler address those issues. This review does not establish native
terminal graphics compatibility or human preference for the animation designs.

Licensing was pending at this point, with MIT as the intended direction. *(Superseded
2026-10-26: the project is GPL-3.0-or-later and keeps Mutagen; see `licensing.md`.)*
No replacement, license selection, publication, or commit was made as part of
this visual refinement.

Additional findings during verification:

- A late table-highlight event could arrive while the UI was being removed.
  Rendering callbacks now check both application lifetime and table availability.
- The first stale-cover test changed internal lists without updating browser rows;
  a legitimate highlight then cleared the image. The test now navigates between
  two real album rows while the earlier decode is held, exercising the user path.
- A plain pseudo-terminal did not answer the graphics capability query. The image
  library fell back to character cells and the application continued normally.
  The CLI suppresses that expected probe warning, and `--help` / `--version` no
  longer import the graphics layer or query terminal input.
- Cover sizing preserves image proportions, rather than stretching to fill the
  available rectangle. The selected-track detail hides in shorter layouts.

With MIT then the intended direction, an isolated, read-only TinyTag 2.3.2
comparison read all 65 local tracks and matched the current normalized metadata
fields and all 62 embedded covers byte-for-byte. Maximum duration delta was about
0.073 seconds; the sample covered MP3/M4A only. Runtime dependencies were
unchanged. *(Superseded 2026-10-26: Mutagen is kept under GPL; no replacement is
planned.)*

### Refinement verification results

| Check | Result |
| --- | --- |
| Full automated suite, Python 3.13.12 | 31 passed |
| Full automated suite, Python 3.12.12 | 31 passed |
| Ruff lint and formatting | Passed |
| Source distribution and wheel | Built; new runtime modules and stylesheet included |
| Package contents | No music, artwork previews, local database, or private test directory |
| Documentation links and personal-path scan | No missing local links or personal paths in source/tests/docs |
| Real mpv with null output and a local M4A album group | Cover loaded; play/pause and the animation frame checked |
| Interface captures | Inspected at 80 × 24, 120 × 36, and 160 × 44 using the colored image fallback |
| Normal CLI in a 120 × 32 pseudo-terminal | Indexed 65 tracks, rendered fallback cover, quit cleanly |
| Original music collection | All 67 file hashes unchanged |

The new automated coverage checks deterministic, varied, fixed-size ASCII frames;
pause/resume timing; stable seeds across seeks; disabled timer behavior; keyboard
focus; saved-seed persistence; embedded front-cover preference; corrupt/missing
and oversized artwork; and stale background artwork during real row navigation.

Full-resolution Kitty/Sixel rendering, Linux, human listening quality, and the
artistic success of these first two animation families remain unverified. The
screenshots and music used for local checks remain outside the public package.


## 2026-10-13: replacement format scope clarified

The owner confirmed that a metadata replacement must support all of Kirlian
Terminal's formats, and acceptance requirements were recorded, separating complete
player format coverage from Mutagen's broader editing features. This changed
requirements documentation only; no runtime dependency was replaced.
*(Superseded 2026-10-26: with GPL chosen, the replacement review was closed and
those requirements removed from `licensing.md`.)*

## 2026-10-13: blank artwork in Ghostty

The owner reported visible album details with a blank image area in Ghostty.
Earlier captures forced half-cell rendering; they did not exercise native
graphics and therefore did not establish that native covers worked.

A controlled reproduction with the installed Textual and textual-image versions
found that `NO_COLOR` changes the foreground RGB identifier in Kitty Unicode
placeholders. The transmitted image ID and the rendered placeholder ID then
disagree. This is a confirmed failure path, but the owner's Ghostty environment
has not been inspected, so it is not established as the cause of that report.

Automatic mode now selects compatible colored blocks in Ghostty, with explicit
native rendering available through `--artwork native` or `c`. The shortcut keeps
the current decoded cover and stores the preference. `--artwork blocks` forces
the fallback on launch; `--artwork auto` overrides a saved choice. Under
`NO_COLOR`, grayscale blocks are mandatory to avoid the reproduced failure.
The tradeoff is reduced cover resolution while native rendering is investigated.

The computer-use tool blocks access to Ghostty. No alternate tool was used to
inspect or control its window. Native visual verification remains outstanding;
the compatibility path can be checked by the owner after restarting the player.

Verification for this change:

- Five new tests pass: automatic Ghostty selection, explicit native selection,
  native placeholder IDs remaining consistent in color mode, safe grayscale
  fallback, and switching/persistence without changing playback or selection.
  Native protocol writes are captured in tests, not sent to a real terminal.
- The existing artwork and application checks pass, including stale loads and
  input focus. A new render assertion initially ran before image layout completed;
  it now waits for the UI refresh before examining rendered cells.
- The real-mpv/null-output walkthrough loaded a local cover, played and paused,
  and resized through 160 × 44, 80 × 24, and 120 × 36. The 160-column capture was
  visually inspected. This time it used normal automatic selection with Ghostty
  environment detection, without replacing the application's image widget.
- CLI help lists the display override; Ruff lint and formatting pass.
- Full automated suite on Python 3.13.12: 36 passed, none skipped.

## 2026-10-13: listening interface design studies

The owner requested a discussion and mockups of a more considered play bar,
setup, personalization, and the Kirlian logo. Created an isolated interactive
study comparing a fine filament ribbon with a compact orbit. It includes a
folder/setup preview, three palettes, motion and character choices, the supplied
wordmark reference, and a proposed character-based logo fallback.

The browser study's play/pause, frozen frames, setup validation/progression,
appearance changes, and narrow-width layout were checked. It plays no audio,
reads no music folder, and does not apply preferences to the terminal player.
Browser graphics and font rendering are not native-terminal verification.

Recorded the proposal and outstanding acceptance checks in `design-studies.md`.
No terminal runtime code or dependencies changed in this exploration.

## 2026-10-13: filament ribbon, branding, and personalization

The owner accepted the filament study and requested its implementation, the logo,
local personalization, and sharp native covers. They also asked for broad terminal
compatibility. The player now has a full-width three-row Braille/ASCII filament,
separate thin progress line, title/artist hierarchy, and quieter controls. Stopped
playback has its own indicator. New songs choose filament seeds; existing saved
seeds still load. Pause and Still freeze the clock; Off retains layout space.

The `p` page previews three palettes, motion, drawing characters, and the header.
Keep saves, Cancel restores, and Reset previews defaults. It reuses the live player
and retains the current queue and browser selection. The folder prompt introduces
local playback with optional personalization afterward.

The graphic header uses packaged SVG outlines and a PNG of the existing brand,
with a compact text fallback. Font files and private reference screenshots are not
included. Brand/font-derived artwork rights remain a publication review item.

Native image work removes the automatic Ghostty block workaround, raises the
bounded cover copy to 1024 pixels per edge, and reduces the LRU to 12 images.
Kitty placeholders bypass display color filters and retain truecolor serialization;
NO_COLOR grayscales the actual cover pixels instead. Targeted image-ID cleanup lets
the cover and logo coexist. The old path could corrupt placeholder IDs or delete
unrelated placements. These reproduced failure paths do not prove the original
owner-reported blank cover had exactly the same cause.

Compatibility defaults now include an explicit no-artwork option, ASCII drawing
override, conservative TERM=linux choices, and a Warp exception for its documented
partial Kitty implementation. The terminal matrix records expected modes separately
from verified behavior. CI configuration now includes macOS and Ubuntu with Python
3.12/3.13; those remote jobs have not been run from this local task.

Verification:

- Real mpv with null audio output played and paused a local album. The cover loaded
  at 600 × 600; the player resized through 160 × 44, 80 × 24, and 120 × 36, preserving
  at least eight table rows at the smallest size and no horizontal table scroll.
  Text/fallback screenshots were inspected; they do not show native terminal images.
- A separate owned pseudo-terminal answered the real capability query, ran the full
  Textual application, opened/cancelled preferences, resized, and exited. With
  NO_COLOR and a 256-color TERM but no COLORTERM, its final output transmitted a 210 × 60
  wordmark, a 340 × 340 cover, and a 200 × 200 resized cover as PNG, preserved
  all RGB image identifiers, and deleted all three image IDs individually. This validates output, not emulator pixels.
- Wheel/source builds succeed and the wheel includes the SVG/PNG brand assets without
  font binaries or music. CLI help exposes artwork and character overrides.
- All 67 files in the retained music integrity manifest match their original hashes.

Direct Ghostty/Terminal.app visual checks remain unavailable because the computer-use
integration blocked access to those applications. No alternate UI access was used.
No actual Kitty, Warp, Linux console, SSH, or multiplexer visual session was verified.
Human listening quality and full-song comfort with motion also remain for review.

Final checks for this pass: the complete automated suite passed (48 tests on
Python 3.13.12), then an additional responsive-caption regression passed after
reserving space below covers. Ruff lint/formatting pass. The final native-output
check and distribution build also pass. The checks cover legacy settings,
preference preview/cancel/persistence, seed and playback isolation, ASCII and
Braille dimensions, native identifier serialization, fallback selection, and
existing library/player behavior. Test corrections explicitly fixed the desktop
TERM environment and waited for native image layout before reading its cells.

The native-output harness waits for player readiness and the loaded cover before
exercising the interface; a fixed four-second startup deadline proved unreliable
under concurrent tests. This was a harness timing correction, not a terminal
compatibility result. Cover sizing now reserves room for the record caption at
120 × 30, 120 × 36, and 160 × 44.

## 2026-10-13: Linux console artwork default corrected

The owner clarified that block artwork is welcome on Linux. The earlier no-artwork
console default was unnecessarily restrictive. Linux terminal applications can use
native image support when available; the bare virtual console (`TERM=linux`) now
defaults to block covers with ASCII ornament. Explicit display preferences still
win, and `--artwork off` remains optional. Updated the compatibility documentation
to distinguish the operating system from the terminal's rendering capabilities.

The focused console regression passes: with TERM=linux it loads a generated cover,
renders actual block glyphs, keeps ASCII ornament, resizes to 80 × 24, and invokes
the expected album playback. Ruff lint and formatting checks pass. This is a
simulated terminal environment; physical Linux console verification remains open.


## 2026-10-13: artwork-derived filament colors

Implemented the owner's request to derive ASCII colors from the album palette.
Up to three local cover colors blend along the ribbon; brighter tints indicate
played progress. Both fine dots and plain ASCII use this palette. Theme choices
continue to affect the rest of the interface and supply a missing-cover fallback.
Colors follow the playing album rather than the browsing selection, including
when the cover pane is hidden or artwork display is off. A stale decode cannot
replace the current album's palette. No song, tag, or cover file is written.

Focused extraction, playback isolation, stale-result, animation, and preference
checks pass (24 tests). Generated covers verify deterministic hue selection,
neutral artwork, source immutability, and at least 4.5:1 contrast for the tested
solid colors against the app background. This does not certify every terminal's
palette conversion or font rendering.

The owner also reports artwork still not appearing. Read-only app metadata identifies
Ghostty 1.3.1 (15212), which supports the relevant image protocol. A restart with an
explicit native-rendering override was requested to distinguish an old running
process from a remaining rendering failure. No visual success is claimed from
protocol support or prior output-only tests; current symptom confirmation is pending.

The complete suite passes after this change: 57 tests on Python 3.13.12. Ruff
lint/formatting and the wheel/source build pass. A real-mpv/null-output walkthrough
loaded a local album and its palette, paused, and resized through the existing
three viewport sizes. The fallback rendering was visually inspected with the
cover-derived blue filament. This is not verification of the owner's native-image
failure, which remains open pending the current runtime symptoms.

## 2026-10-13: native artwork failure confirmed; isolated diagnostic

The owner confirmed that a forced-native restart is still blank, and that pressing
`c` displays block artwork. This confirms decoding and narrows the failure to
native display. The earlier restart question is resolved; native artwork is not
visually accepted. Inspection of retained terminal output found correctly ordered
image transmission, placement, and placeholder IDs; this still cannot establish
what Ghostty paints.

Added `--check-artwork`, an isolated comparison of a generated picture using direct
Kitty placement, the player's placeholder encoder outside Textual, and block
rendering. It reports terminal acknowledgements separately from the owner's
visibility observation. It opens no library, requires no mpv, and changes no
preferences. The player's native renderer is unchanged while the failure is
being isolated. The next required evidence is this report from the affected
Ghostty session. Direct inspection of that application remains unavailable.

Focused diagnostic tests pass: reply parsing/deadline, real owned-PTY execution
with an injected placement error, normal completion and cancellation, decoded PNG
payloads, terminal-mode restoration, and absence of library creation. This is
diagnostic verification rather than a claim that native artwork is fixed.

The owner then reported only sample C visible, followed by the full diagnostic:
direct PNG returned `EINVAL: unsupported format`, and the player placeholder
returned `ENOENT: image not found`. The environment identified Ghostty with
truecolor, with neither tmux, screen, nor NO_COLOR set. The checked local Ghostty
configuration did not explicitly disable images. This is concrete evidence of
rejected image transmission, rather than a missing local cover.

Changed both native covers and branding to zlib-compressed RGBA pixel transmission.
This retains alpha and lossless pixel data without requiring the terminal PNG
decoder. The diagnostic uses the new transport too and prints the format in its
report. A controlled pseudo-terminal now simulates successful generic capability
queries but rejection of PNG, verifying that direct and placeholder paths load
their RGBA pixels successfully. A separate round-trip test checks exact RGBA bytes,
alpha, chunk limits, and continuation fields.

The full test run also exposed an intermittent, persistent zero-height image
layout, rather than simply a slow paint. The upstream automatic height calculation
can read the child's old zero width before layout. Covers now get explicit bounds
from the decoded aspect ratio and real terminal cell dimensions. A late-load test
checks positive painted areas and portrait, landscape, and square proportions.
This fixes a second blank-artwork failure but does not explain the separate PNG
rejection outside Textual.

The ten focused cover/transport checks pass. The owned full-app pseudo-terminal
also exits cleanly after preferences and resize: both wordmark and cover transmit
valid RGBA data, retain exact placeholder IDs, and receive targeted cleanup.
The owner has been asked to verify the actual cover and logo after this change;
visual acceptance remains pending.

The broader resize check caught a stale-geometry case after shrinking the window.
Moved cover bounds to the record pane's own resize event, after its dimensions
are available. The focused resize and cover suite passes (seven tests), including
caption containment at 160 × 44, 120 × 36, and 120 × 30.

Final verification after these fixes: all 62 tests pass on Python 3.13.12; Ruff
lint/format checks and both distribution builds pass. The final owned-PTY run
also passes with RGBA wordmark and cover data, exact RGB placeholder IDs, resize,
and targeted cleanup. No real Ghostty visibility confirmation has been received
for the new transport yet, so native visual acceptance remains open.

## 2026-10-13: native images remain blank; separate format evidence

The owner reports both native cover/logo still blank after restarting with the
raw-pixel change. That change is not a verified resolution. The local entry point
loads this checkout's renderer, but the affected session's loaded code and actual
terminal responses still need confirmation. Installed Ghostty bundle metadata
alone cannot identify the running terminal implementation.

Extended `--check-artwork` to version 2: six labeled samples compare uncompressed
RGB, uncompressed RGBA, compressed RGBA, PNG, the real player placeholder encoder,
and blocks. It queries the running terminal version and can save an explicit local
JSON report via `--artwork-report`, including loaded source fingerprints and
dependency versions. This avoids repeated manual transcription and distinguishes
format acceptance from placement and actual visibility. No production rendering
or saved preferences were changed in this step.

All six focused diagnostic checks pass, including owned-PTY execution with raw
RGBA support versus RGB-only support, rejected PNG, correct per-format errors,
normal exit/cancellation, terminal-mode restoration, saved reports, and no library
creation. Focused Ruff checks pass. The affected Ghostty session must still run
the comparison; automated fake-terminal replies are not visual acceptance.

## 2026-10-13: raw transport accepted; responding host is libghostty

Read the owner's saved report and matched both loaded source fingerprints to the
checkout. The result is **F only**: uncompressed RGB/RGBA, compressed RGBA, and
player placeholder placement all return `OK`; PNG returns `EINVAL: unsupported
format`. The live terminal version reply is **libghostty**, although the process
environment says Ghostty 1.3.1. Raw image transport now succeeds in that session;
none of its native samples are visually rendered.

Checked upstream source: the library returns `libghostty` when its embedding host
does not supply a version callback, and can reject PNG when no decoder is supplied.
The standalone application's response contains `ghostty` and its version. This
corrects the earlier assumption that the observed session was necessarily the
standalone Ghostty application. Which host application owns the session is still
awaiting the owner's confirmation; no blanket Codex or libghostty capability
claim is inferred from the version string.

Automatic mode now queries the live identity before Textual starts and chooses
block covers plus the character logo for the generic libghostty identity. The
query is cached, capped at half a second, and restores input mode. Missing replies
and identified native terminal apps preserve existing detection. Explicit native
mode remains available, including for future embedded hosts with full rendering.
The diagnostic explains the distinction. Saved native overrides are preserved;
`--artwork auto` opts into automatic selection for a launch.

Verification: all 67 tests pass on Python 3.13.12, including three real owned-PTY
startup cases for embedded, identified, and unanswered terminal identity. They
check cover/brand selection, native override, query caching, and input-mode
restoration. Ruff lint/format checks and both distribution builds pass. The
owner's F-only observation remains the visual receipt for the embedded session;
sharp cover/logo rendering in a standalone terminal still needs confirmation.

## 2026-10-13: standalone artwork and embedded fallback visually confirmed

The owner supplied two screenshots, explicitly identifying the first as the
separate Ghostty app and initially identifying the second as the Codex terminal
panel. **Correction:** the owner subsequently identified it as Herdr; see below.
The standalone
view shows a sharp album cover and the full graphic Kirlian wordmark together.
The embedded view shows the same selected album with the block cover and the
character wordmark. Both views show the library while playback is idle.

This confirms visible covers for the demonstrated views, with block fallback
in the embedded host. It does not resolve native artwork in Herdr. The distinction is
now supported by visible output, not just protocol acknowledgements. It does not
certify all terminals, versions, album switching, resize, motion, or cleanup.
Updated the current compatibility matrix and README. No renderer changes or
new automated test run were needed for this documentation-only evidence update;
the preceding implementation's 67-test pass remains the latest automated check.
Screenshots containing the personal library were not copied into public assets.

## 2026-10-13: character branding and Herdr configuration

The owner corrected the embedded host to **Herdr** and requested a terminal-native
version of both the sunburst and wordmark. The header now draws original lowercase
letter strokes and eight open-center rays into two rows of Braille characters,
with a separate plain-ASCII emblem and ordinary lettering. It uses ordinary text
in every terminal and
has no dependency on image protocols, Pillow, or a custom font. Drawn / Simple
options reuse the existing stored preference values. Short windows retain the
one-line mark. Font-derived SVG/PNG assets are removed from the public package.

The installed Herdr client and server are both 0.8.2. Its generated default config
sets experimental Kitty graphics off; the user's existing config did not override
that setting. Backed up the config, enabled `[experimental] kitty_graphics = true`,
and reloaded it. The server returned `applied` with no diagnostics. No client,
server, pane, or agent process was stopped. The owner initially reported a sharp
cover but corrected the observation: that session was not Herdr. Herdr still
shows a blank native image. Client reattachment needs confirmation. Automatic
mode retains the conservative
libghostty fallback, so the verification launch must use `--artwork native`.

The pinned image dependency already wraps graphics in tmux passthrough envelopes.
Extended owned-PTY tests to cover that transport, and made the isolated diagnostic
wrap its identity query too. The first synthetic mux test incorrectly discarded
plain DA queries that tmux itself answers; the model now retains those while
unwrapping complete DCS envelopes. Herdr presence is included in saved diagnostics
without exposing socket paths or pane IDs. No real tmux binary is installed here.

Native cover visibility in Herdr remains unresolved. Dynamic pane changes,
resize, and cleanup also require real-host review; none is inferred from protocol
acknowledgements or headless tests. Final automated results are recorded below.

The owner's screenshots showed that the first three-row dotted wordmark was too
large and its letterforms felt off. Reduced it to two rows (24 reserved columns
instead of 34), redrew letters on an eight-dot grid, simplified the radial mark,
and added a blank row above it. The masthead is one row shorter overall. The
owner cannot check Herdr again right now and has agents running there; further
client testing is deferred and no server restart is authorized or performed.

Verification: the full 75-test suite passes, including the owned-PTY tmux
transport and identity cases. The real-music headless walkthrough played through
an owned silent-output mpv instance, paused, rendered 160 × 44 / 120 × 36 / 80 × 24,
opened personalization, and shut down its player. Screenshots confirm the smaller
header and usable compact layout. These checks do not establish audible quality
or native Herdr visibility. Lint, formatting, wheel and source builds pass; the
package no longer contains the earlier raster/vector wordmark assets.

After the final logo size and spacing adjustment, all seven focused header,
appearance, and tmux diagnostic checks pass. The diagnostic test deadline allows
for slower hosts while the actual terminal reply reads remain bounded.

## 2026-10-13: native cover visible and interface tightening

Following the Herdr setup discussion, the owner reports “works!” and supplies a
new screenshot with a sharp album cover and the reduced character header. This
is a visual receipt for the shown session; the image does not contain terminal
identity. The exact reattachment steps and dynamic multiplexer behavior are not
established. The agent did not restart Herdr or interrupt its running agents.

The next request is to tighten the interface as a whole. Consolidated collection
heading/count, removed the repeated root breadcrumb, aligned duration cells,
overrode the table's gray focus tint, and made the inactive sidebar selection
quieter. Search and personalization remain above; contextual playback and browsing
hints, pattern, help, quit, and volume now occupy one footer row. Full shortcut
coverage remains in Help. Empty status text and empty note dividers are hidden;
the idle player uses one clear invitation and omits meaningless 0:00 / 0:00 time.
The play bar is shorter without reducing the filament's three-row drawing area.

The 13 focused navigation, resize, branding, and appearance checks pass. A
read-only real-library walkthrough used an owned mpv process with silent output
to play, pause, resize, and open/cancel preferences; screenshots were inspected
at 160 × 48, 120 × 36, and 80 × 24. Native graphics remain covered separately
from these block-artwork headless previews. No music files, artwork transport,
font assets, or Herdr settings are changed in this pass.

Final verification: all 75 tests pass, including native-cover identifiers and
cleanup, multiplexer transport, input focus, queue behavior, appearance rollback,
and real-engine integration. Ruff lint/format checks and source/wheel builds pass.
The final preview also confirms ellipses on long rows and a single control row.

## 2026-10-13: cover latency and interface responsiveness

The owner reported lag and slow album loading. Inspection and local measurement
found repeated Kitty image uploads on repaint, synchronous native-image preparation,
an unconditional 120 ms cover debounce, row rebuilding on table resize, and layout
requests from fixed-size animation/player updates. Removed that redundant work;
see the architecture entry for cache ownership, bounds, and invalidation rules.

The read-only measurement used a copy of the existing 51-album library index,
Python 3.13, Textual 8.2.8, textual-image 0.14.1, and a 160 × 48 headless app with
10 × 20 pixel cells. It selected ten albums once, revisited the same ten, and
requested ten repaints of the final cover. The environment had NO_COLOR enabled.
Native protocol messages were collected in memory rather than sent to a terminal;
the player was a test double. Private music, paths, screenshots, and raw profiling
artifacts stay outside the public repository.

| Measurement | Before | After |
| --- | ---: | ---: |
| First-visit cover latency, median | 267 ms | 180 ms |
| Cached cover latency, median | 103 ms | 11 ms |
| Extra image uploads for ten cached visits | 10 | 0 |
| Extra uploads for ten unchanged-cover repaints | 10 | 0 |
| Image payload for those ten repaints | 1.63 MB | 0 |
| Event-loop scheduling delay, 95th percentile | 89 ms | 15 ms |
| Longest event-loop scheduling delay in the run | 265 ms | 46 ms |

These are local observations, not terminal-to-screen guarantees or statistically
controlled performance claims. Filesystem/CPU conditions varied: separate source
decode measurements across all 51 albums had medians of 31 ms before and 15 ms
after, although the decoder itself was unchanged. “First visit” means an empty
application artwork cache, not a cold filesystem cache. Before, timing ended when
the native placement command was collected; after, it ended when the current
cover's placeholder rows were renderable, polled every 5 ms, since cached visits
correctly emit no new placement command. Actual Ghostty/Herdr drawing and transport
latency are excluded. The protocol-byte and upload counts directly establish the
removed work without relying on timing comparisons.

Added regressions for upload reuse in color and grayscale, bounded native-cache
eviction and complete ID cleanup, navigation while image encoding is deliberately
blocked, rejecting a late image, preserving table rows/selection on resize, and
avoiding extra layout/animation work on position events. Existing focused cover,
artwork, animation, and palette checks passed before the final full-suite run.
No Herdr settings or processes were changed.

The real-library walkthrough caught stale horizontal scroll width after narrowing
the window. Column changes now invalidate DataTable's cell caches and recompute
scroll dimensions without rebuilding rows; the resize test asserts both preserved
selection and no horizontal overflow. The final 18 focused app/cover checks pass.
The walkthrough uses an owned mpv process with silent output, plays and pauses a
local album, checks 160 × 48 / 120 × 36 / 80 × 24 layouts and personalization,
and confirms the player exits. Inspected block-artwork previews retain the intended
layout. This does not establish audible quality or physical-terminal latency.

Verification: the full 80-test suite passed. After the final column-dimension and
cached-resize cancellation adjustments, all 18 app/cover tests and the real-engine
walkthrough passed again. Ruff lint/format checks and source/wheel builds pass.

## 2026-10-14: 100 ribbon patterns

The owner reports that the performance pass feels better and requests around 100
permutations. Added exactly 100 versioned recipes: ten named profiles across
filaments, tides, braids, ripples, orbits, fronds, mycelium, embers, seeds, and
constellations. New songs and `x` use the same session shuffle pool, preferring a
different family and exhausting its entries before refilling. Save/recall status
shows readable names. Saved version-1 seeds retain their original frames.

The arrangement, album-derived colors, frozen pause behavior, separate playback
progress, and 10 Hz limit remain intact. The catalog stores small recipe identities,
not prerendered sequences. Its renderer writes directly into three rows of cell
bit masks and retains no motion history. The initial ellipse sampler was too
expensive at 400 columns; it now caps ring count and samples visible columns only.
No artwork transport, library scanning, mpv behavior, or Herdr settings changed.

The 39 animation checks pass, covering catalog count and unique names, all 100
distinct frames in both modes at useful widths, deterministic motion, width caps,
two complete shuffle cycles, recall at the end of a pool, version validation,
legacy frame hashes, and the existing pause/seek/save/input-focus behavior.
The earlier 24 focused animation, palette, and appearance checks also passed.

Added reproducible preview and benchmark scripts. Preview SVGs use actual renderer
output and a fixed illustrative palette, with local fonts and no external assets.
Reviewed representative family drawings; generated and validated the complete
100-pattern sheet and the ASCII sheet. These are static composition checks, not
claims of smooth rendering in every physical terminal.

Pure frame-generation benchmark, 20 frames per recipe across all 100 recipes:

| Width | Dot catalog mean | ASCII catalog mean |
| --- | ---: | ---: |
| 76 columns | 0.264 ms | 0.172 ms |
| 156 columns | 0.271 ms | 0.341 ms |
| 400 columns | 0.656 ms | 0.900 ms |

At 400 columns the slowest recipe's mean was 1.846 ms in dots and 2.698 ms in
ASCII. The previous filament measured 0.493 ms at 156 columns and 1.291 ms at
400 columns in dots in the same script. These are local observations under varying
machine load, not timing assertions in CI. They exclude Textual, terminal drawing,
palette styling, and artwork; they do not measure end-to-end interface latency.

A read-only real-library walkthrough with an owned silent-output mpv process
played and paused music, displayed a new Mycelium recipe with album colors,
checked 160 × 48 / 120 × 36 / 80 × 24 layouts and personalization, and shut down
its player. This verifies the exercised behavior, not audible playback quality.
Final verification: all 105 tests pass, including native cover caching/cleanup,
input focus, player events, album ordering, queue behavior, appearance rollback,
and the new catalog/compatibility checks. Ruff lint/format checks and wheel/source
builds pass. The new drawing was inspected in the real-library headless player;
physical-terminal motion quality remains a listening-session check.

## 2026-10-14: personalization feedback and save ordering

The owner reports that changes do not appear or save. Normal keyboard and mouse
selection/commit checks passed, but a new regression reproduced an ordering edge:
changing a Select value and saving before its queued change message arrived wrote
the previous settings. Save now captures the values shown in the controls. This
reproduced edge does not establish the cause of the owner's terminal experience.

Replaced the ambiguous Keep label with Save changes, added Ctrl+S, an accent sample,
and explicit unsaved/saving/saved feedback. Contextual explanations cover the
unchanged album-derived ribbon palette, paused motion, compact header, and grayscale
under NO_COLOR. Reset remains a preview; Cancel discards the preview. Writes run
off the UI loop, and failed writes retain the preview with retry/cancel controls.

Verification includes the stale-message regression, keyboard-only edits and fresh
app/database reloads at 120 × 36 and 80 × 24, reset/cancel after a saved preference,
and a deliberately blocked and failed database write while player events continue.
User settings were inspected read-only; tests use temporary databases. No Herdr
configuration, other running sessions, or music files were changed. Actual
Ghostty/Herdr interaction remains to be confirmed by the owner.

The broader run exposed an existing cache-test setup race: its first cover was
rendered at the initial full width before the square layout settled, so revisiting
that cover at square dimensions correctly required another upload. The test now
settles its initial dimensions before measuring reuse; its explicit resize and
image-ID cleanup assertions remain. No artwork renderer changes were needed.

## 2026-10-21: empty `~/Music` scan explained

The owner launched with `--music "$HOME/Music"` and saw no music. On this Mac,
`~/Music` holds only the Apple Music library folder, which macOS privacy controls
refuse to the terminal (`Operation not permitted`); the scan finished with
"Indexed 0 files · 1 unreadable files/folders skipped", which did not say why.
Spotlight lists no audio under `~/Music`; local files are in other folders.

Scans now count permission-denied folders. A finished scan with no music says
whether folders were blocked (with the macOS Privacy & Security location, or a
permissions hint elsewhere) or the folder simply has no supported files, and points
to `f` to choose another folder. A regression test covers a denied subfolder.
Smoke: scanning the real `~/Music` read-only reports one blocked folder.
Whether granting access exposes any downloaded (non-streaming) files is unverified.

## 2026-10-26: GPL license, saved playlists, and Exa song facts

The owner chose GPL-3.0-or-later over MIT: the existing `LICENSE` already held the
GPL-3.0 text and Mutagen is GPL-2.0-or-later. `pyproject.toml` now declares
`license = "GPL-3.0-or-later"`; README, `licensing.md`, and the architecture's
deferred list agree. The owner also brought saved playlists and song facts
forward, chose Exa over Perplexity, and supplied the "Behind the record" mock.

Changes:

- `playlists.py` and the Playlists / playlist views: create, rename, delete
  (confirmed), add songs/albums/queue items with `+`, reorder with `J`/`K`, remove
  entries with `d`, play in saved order, append a playlist with `a`, and find
  playlists in search. Duplicates are kept; missing files show as unavailable.
- `facts.py`, the `i` setup dialog, and the fact card: Exa `/answer` with
  `outputSchema`, citation-matched facts only, `keyring` credentials with
  environment and session fallbacks, a local `facts` table, a two-second start
  delay, and stale-answer rejection. `[`/`]` step through facts; `o` opens the
  source. One new dependency: `keyring` 25.7.0 (MIT) with its jaraco/more-itertools
  helpers.
- Tests never touch the real credential store: `conftest.py` installs an
  in-memory keyring for every test.

Checks: `uv run ruff check`, `ruff format --check`, and `uv run pytest` — 120
passed, including new playlist storage tests (order, duplicates, move boundaries,
delete leaving files and other playlists), an app walkthrough (typing a playlist
name with `q`/space, saved-order playback skipping a missing file, move, remove,
confirmed delete), fact parsing (citation matching, control stripping, non-web
URLs, string answers), request errors (401, timeout) and metadata-only payloads,
credential precedence and keyring failure, stale-answer rejection with per-song
caching, and key entry through the setup dialog. A throwaway Textual render at
150 × 46 with a fake player showed the card matching the mock's layout and a
playlist with a duplicate and an unavailable entry.

Not verified: no live Exa request was made (no key in this environment), so the
exact `/answer` structured-output shape is taken from Exa's documentation; the
first real use should confirm facts appear. Linux credential-store behavior and
the browser opener for `o` were not exercised. Real-terminal rendering of the card
and dialogs, and a listening pass through a saved playlist, remain manual checks.

Open before making the repository public (supersedes the 2026-10-13 checkpoint
list, which predates the GitHub remote and first commits):

- The `checks.yml` workflow has not yet run on GitHub; confirm it passes on push.
- A complete real-album listening pass, a Linux install/playback run, and a list
  of terminals actually checked are still required by the specification.
- One live song-facts check with the owner's key for the chosen provider.
- The repository is still private; making it public is the owner's step.

## 2026-10-26: choose the song-facts provider

The owner asked to let listeners pick their API provider instead of forcing Exa.
The `i` dialog now has a Provider choice (Exa, OpenAI, Anthropic, Perplexity,
Parallel) with per-provider key hints, keychain entries, and environment
variables. `facts.py` replaces the Exa-only request with a provider table, three
response readers, and the shared retrieved-page check. API shapes were taken from
each provider's current documentation; Perplexity's Sonar API is retired, so the
Agent API is used. No new dependency.

Checks: `ruff check`, `ruff format --check`, and `pytest` — 125 passed. New
parametrized tests send a request through each provider with a fake transport
and a response in that provider's documented shape: they confirm the endpoint,
that the key travels in the headers, that the body carries metadata but not file
paths, and that an invented URL is dropped while a retrieved one is kept. Other
tests cover duplicate source entries merging titles and dates, provider-named
errors, per-provider credentials with environment and session fallbacks, and the
dialog flow (choosing OpenAI, typing `q no` into the key field without triggering
shortcuts, the key landing under `openai` only). A throwaway render at 120 × 40
showed the provider list and the updated hint and placeholder.

Not verified: no live request to any provider. Default model names
(`gpt-5.4-mini`, `claude-haiku-4-5`) were current in the providers' docs on this
date and will need updating over time.

## 2026-10-26: license surfaces, facts loading rhythm, and `--check-facts`

License: removed the MIT/TinyTag replacement sections from `licensing.md` and
rewrote it around the settled GPL-3.0-or-later decision, with a table of every
place the license is stated. Added `SPDX-License-Identifier: GPL-3.0-or-later`
headers to all 37 Python and TCSS source, test, and script files; `--version`
now prints the license and no-warranty line; CONTRIBUTING states contribution
terms; the architecture intro no longer says licensing is under review. Earlier
dated entries here that assumed MIT are kept as history, marked superseded.

Loading indicator: while a facts request is in flight, the card shows the playing
title as a step pattern with a walking playhead (see architecture). Live check:
`kirlian --check-facts [PROVIDER|all]` makes one real request and reports pages
retrieved and each fact's pass/fail.

Checks: `ruff check`, `ruff format --check`, `pytest` — 127 passed. New tests
cover the title-to-rhythm mapping (syllables, digits, rests, 16-step cap, empty
titles), the card switching from rhythm to fact with the timer stopped, and the
live check's output and report with a fake transport (kept/dropped facts, a
provider error body printed, the key absent from output and report). A headless
render showed the playhead advancing across "Paris 1919". `kirlian --check-facts
exa` without a key and with an unknown provider exited 1 and 2 with readable
messages.

Not verified: a live request to any provider (the owner is testing with a key);
the rhythm's timing and look in a real terminal.

## 2026-10-26: annotation-style notes, provider order, and key settings

Owner report: a Perplexity key was "added", but nothing changed. Findings on this
Mac: the keychain held only an Anthropic key (`security find-generic-password`
showed one `kirlian-terminal` item), and `facts_provider` was `perplexity`. Facts
were cached per song regardless of provider, so the six songs already answered
by Anthropic kept showing Anthropic's notes. The old dialog also opened with the
provider dropdown focused, so a key pasted right after choosing a provider could
miss the key field. Both causes are removed (see architecture).

Changes: Genius-annotation prompt with `story` / `reading` kinds; per-provider,
versioned cache; ordered providers with fallback on failure; settings screen
(`i`) for adding, rotating, and removing keys, ordering, models, and on/off;
`--check-facts --model`; source labels with the site; relative page ages dropped.

Live check (one billed request, owner's Anthropic key, `claude-sonnet-5-5`):
"Electronic Performer" by Air returned 3 notes in 17.5 s from 34 retrieved pages;
all 3 passed the source check. One `reading` (the lyrics' MIDI clock and 12-bit
samplers casting Air as Kraftwerk-style machines) and two `story` notes (first
song from the sessions, per Nicolas Godin; the build that never drops, per
Uncut). The earlier prompt's notes for the same song were engineers, studios,
and mixing credits. Not evaluated: other songs, other providers live, Opus.

Checks: `ruff check`, `ruff format --check`, `pytest` — 131 passed. New tests:
the settings walkthrough (key typed with `q`, space, `J`, `t` without triggering
shortcuts; order, model, on/off persisted; keys kept when turned off), fallback
on a provider error with the right model per provider and the card's reading and
"via" labels, primary recovery after settings close, per-provider cache, cache
version cleanup, config migration and validation, kind handling, and labels.

## 2026-10-28: clearer song-notes settings

Owner screenshot: Anthropic had a key but was "–" while Perplexity was "1", the
model column's purpose was unclear, and reordering was hard. Reworked the screen
as recorded in architecture (role-sorted rows, selection follows the provider,
direct `1`-`5` placement, per-row explanation and applicable actions, model
picker with descriptions). Model descriptions are relative guidance from the
providers' positioning, not measured quality or price.

Checks: `ruff`, full `pytest` — 131 passed. The settings test now walks: add an
OpenAI key (typing `q`, space, `J`, `t` into the key field), add Anthropic as a
fallback and confirm the detail line, move it up with `K` and confirm the row and
selection moved, place OpenAI first with `1`, pick Haiku from the list and then
the default again (override removed), turn notes off, and reload the saved order.
Headless renders at 120 × 42 checked the table, detail line, and model list.
Not checked in a real terminal.

## 2026-10-28: header type mark

Replaced the drawn Braille wordmark with a one-line type mark (`✺  kirlian`) and
removed the Header preference (see architecture). Checks: `ruff`, full `pytest` —
131 passed. Brand tests now check the mark is one line and stays clear of the
search hint at 120 × 36, 80 × 24, and 160 × 48 for native, block, and no artwork;
ASCII characters give `*  kirlian` and an ASCII fact spark; and an appearance
saved with the old `logo` key loads without it. A headless 120 × 30 render showed
the mark centered in the shorter masthead. Glyph rendering in the owner's
terminal font is not yet checked.

## 2026-10-28: multilingual interface

Added interface languages (see architecture): `i18n.py`, eight catalogs of 242
strings, a Language preference under `p`, locale detection, notes in the active
language, and `scripts/i18n_catalog.py`. 257 call sites in `app.py`,
`playback.py`, and `library.py` now go through `_`/`n_`. English output is
unchanged except for corrected plurals ("Indexed 1 file", "1 album", "{n} in
queue") and the help line now says "song notes" instead of "song facts".

Translations were drafted by one AI agent per language and pass the catalog
check; none has been reviewed by a native speaker. Flagged for review: key names
left in English inside sentences ("Pulsa space…"); "fallback" terms (es
respaldo, fr secours, de Ersatz, it riserva, pt-BR reserva, ja 予備, ko 대체,
zh 备用); macOS settings paths written from memory; Korean particles after
placeholders (이(가)); mixed gender in pt-BR "Reserva" descriptions; German
"bewegen" used for both focus and reordering.

Checks: `ruff`, catalog check ("All catalogs cover 242 strings"), full `pytest`
— 162 passed, including locale precedence, saved-choice precedence, fallback,
plural rules, every catalog complete with matching placeholders, every
translation formatting with sample values, a Spanish launch with a language
change that applies only after relaunch (Japanese), and per-language notes
prompt and cache keys. The wheel contains all eight catalogs. Headless renders of
Japanese and German at 120 × 40 showed the main screen, fact card, and settings
fitting; CJK width and font fallback in a real terminal are unverified.

## 2026-10-28: live language switch

Owner report: the language did not change after saving. The saved setting was
`fr` and a relaunch showed French, so the cause was the deferred apply, not the
catalogs. Saving now switches immediately (see architecture). Also fixed in the
same pass: the French "File d'attente" wrapped in the sidebar, and translated
time headers were cut off ("DURACI").

Checks: full `pytest` — 162 passed. The language test now opens an album, selects
the second song, switches Spanish to Japanese with Ctrl+S, and checks the sidebar
is Japanese, the album view and selection are kept, the status confirms, and no
playback command was sent. A headless run against a copy of the owner's library
(French, a song "playing" at 0:30 with a block cover) switched to Spanish with the
cover, progress, and player line intact. Not checked: the switch in a real
terminal with native images and live mpv.
