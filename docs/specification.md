**Kirlian Terminal — implementation handoff**

**The product**

A small terminal music player for people who listen to albums. Fast navigation, a clear view of the record, and occasional context that gives you something new to hear.

Built in Python for macOS and Linux. Intended for a small audience alongside Kirlian’s launch.

The first release should feel complete within a narrow scope: local music, albums, playlists, keyboard control, optional song facts, and small ASCII animations.

**1. Project boundaries**

Build a standalone application in the new directory supplied by the owner.

- Keep it independent of the existing Kirlian application and backend.
- Local playback works offline, without an account or API key.
- Audio stays on the user’s computer.
- Never modify music files, tags, or folder organization.
- Exclude streaming integrations, lyrics, downloads, cloud sync, and Kirlian visual generation from this release.
- Use the existing mockup as visual guidance, not as an implemented application.

**2. Implementation defaults**

| Responsibility | Choice |
|---|---|
| Language | Python 3.12+ |
| Terminal interface | Textual |
| Audio playback | An owned mpv subprocess, controlled through JSON IPC |
| Metadata | Mutagen |
| Library and playlists | SQLite through Python’s standard library |
| Application directories | platformdirs |
| Development and dependencies | uv and pyproject.toml |
| Optional artwork | Add terminal-image support after core playback works |
| Optional facts | One provider integration, added last |

Textual supports background workers for operations that would otherwise block the interface. mpv provides playback commands and events through its documented IPC interface. Use those events as the source of playback state. [Textual workers](https://textual.textualize.io/guide/workers/), [mpv JSON IPC](https://mpv.io/manual/stable/#json-ipc), [Mutagen](https://mutagen.readthedocs.io/en/latest/).

Keep the structure small: interface, library, playback, playlists, animations, facts, and settings. Avoid a plugin system or service architecture.

**3. Main screen**

Use three regions above a persistent playback bar:

- **Navigation:** Albums, Artists, Songs, Playlists, Queue.
- **Browser:** the selected collection, album, or playlist.
- **Context:** modest album artwork, essential metadata, and an optional fact card.

Albums are the default view.

Opening an album shows its tracks in disc and track order, with title and duration. Keep the current selection visually distinct from the currently playing song.

The playback bar shows play/pause state, artist and title, elapsed and total time, progress, volume, and a small ASCII animation.

On narrower terminals, hide the context column first. At 80 × 24, browsing and playback controls must remain usable. Essential controls must never depend on artwork being available.

Visual direction: near-black surfaces, warm bone text, restrained aubergine selection, quiet borders. Use the terminal’s monospace font. Artwork and animation should occupy a small proportion of the screen.

**4. Library and playback behavior**

On first launch, ask for a music folder. Validate it, begin indexing in the background, and show albums as they become available.

- Read embedded tags; use filenames and folders as understandable fallbacks.
- Group albums using album artist and album title, with folder/release information to avoid merging distinct editions.
- Support compilations and multiple discs.
- Sort track numbers numerically.
- Skip unreadable files and show a concise scan summary.
- Persist the library so subsequent launches do not require a complete blocking scan.
- Provide a rescan action.

Prioritize MP3, FLAC, M4A/AAC, Ogg Vorbis/Opus, and WAV. Verify supported files through the installed playback engine; unsupported files must fail visibly without crashing.

Playback rules:

- Enter on an album opens it.
- Enter on a track starts that track in the album or playlist’s ordered queue.
- Enter on a song search result starts its album queue at that song.
- Enter on a queue item jumps to that item.
- Adding an album or song to the queue appends it without interrupting playback.
- Browsing, filtering, or editing a saved playlist does not silently replace the active queue.
- Shuffle and repeat are off initially.

Let mpv own the loaded playlist and track transitions. Do not implement continuous playback by launching a new process for every song.

Pause, resume, seeking, volume, and track changes must reflect actual playback state. Test continuous album playback for audible gaps.

**5. Keyboard contract**

These shortcuts apply in navigation mode:

| Key | Action |
|---|---|
| `j` / `k` | Move down / up |
| `h` / `l` | Back / open |
| `Enter` | Open a collection or play a track |
| `Space` | Play / pause |
| `/` | Search |
| `Esc` | Dismiss search/dialog or go back |
| `Tab` / `Shift+Tab` | Move between available panes |
| `a` | Append selected song or album to the queue |
| `n` / `N` | Next / previous track |
| `H` / `L` | Seek backward / forward five seconds |
| `-` / `=` | Lower / raise volume |
| `v` | Toggle animation |
| `x` | Choose another animation |
| `?` | Show keyboard help |
| `q` | Quit |

Arrow keys should also work.

**Text entry takes priority.** Spaces, letters, and punctuation typed into search, folder paths, or playlist names must not trigger playback shortcuts.

Show a short, context-sensitive shortcut footer. Playlist actions can initially live in a keyboard-accessible action menu.

**6. Search and playlists**

`/` opens immediate local search across songs, albums, artists, and playlists. Group and label results clearly. Matching should ignore case and work with partial names.

Search must not interrupt playback. Escape restores the previous browser position.

Users can:

- Create and rename a playlist.
- Add a song or an entire album.
- Reorder and remove entries.
- Play a playlist in its saved order.
- Delete a playlist without affecting music files.

Preserve intentional duplicate entries. If a referenced file disappears, mark it unavailable and allow removal; do not discard the rest of the playlist.

**7. ASCII animation**

Animations live inside a fixed area of the playback bar. They are decorative in this release; they do not claim to visualize the audio.

Use small procedural generators with seeded variation. Proposed launch target: **eight families with 32 curated seeds each**, producing 256 selectable variations without hundreds of handwritten animation files.

Possible families: filaments, sparks, ripples, orbiting points, drifting dust, branching lines, waves, and small organic forms.

Behavior:

- Randomly select a variation when a song starts.
- Keep that variation throughout playback and seeking.
- Freeze the current frame when paused.
- Resume smoothly.
- `x` selects another variation without changing playback.
- `v` disables animation; remember the preference.
- Keep the region’s dimensions fixed.
- Bound the frame rate, initially around 8–12 frames per second.
- Do not run a redraw loop when animation is disabled.
- Use printable ASCII characters and avoid flashing.

Start with two families for review, then expand the catalogue. Variation should remain recognizable and restrained.

**8. Artwork and context**

Load embedded artwork first, then conventional cover images in the album folder. Load and resize it outside the UI thread.

Artwork is optional. Unsupported terminals get a clean text fallback with album, artist, year, and format.

The fact card contains one short note about the recording, album, personnel, or musical context, accompanied by a source title and URL. Prefer specific information over generic praise.

Facts are explicitly opt-in and use the listener’s API key:

- Explain that artist, album, and song metadata will be sent to the selected provider.
- Never send audio, artwork, or local file paths.
- Fetch after a song has actually started, with a short delay to avoid requests during rapid skipping.
- Request at most once per unique song per application session, unless the user explicitly retries.
- Discard outdated responses when the song changes.
- Keep playback responsive through timeouts, missing keys, and provider failures.
- Display a note only when supporting source material is available. A model-generated URL alone is insufficient.
- Store credentials in the operating system’s credential store where available. Otherwise offer session-only or environment-based configuration.

Implement one provider. Confirm its current API, inexpensive model, and source-retrieval support before this milestone; do not copy the existing Kirlian enrichment pipeline.

The initial playback milestone must make no paid API calls.

**9. Onboarding**

Keep the first run short:

1. Choose a music folder.
2. See albums appear.
3. Open an album and play a song.

Once music is playing, show a dismissible invitation to enable song facts. Skipping it leaves a fully usable player.

If mpv is missing, show a readable explanation and platform-appropriate installation guidance. Avoid a traceback or a screen that appears to work but cannot play.

Remember the library folder, preferences, and playlists. Restore the last listening position in a paused state on later launches.

**10. Build sequence and acceptance criteria**

**Milestone 1 — real local playback**

Deliver the installable Python project, folder onboarding, background indexing, album/track browsing, search, playback queue, and core keyboard controls.

Accepted when:

- A fresh checkout can be installed and launched using the README.
- A real folder can be indexed and a complete album played.
- Pause, seek, next, previous, and volume work.
- Searching and browsing remain responsive during playback and scanning.
- Typing spaces in search does not pause music.
- Paths containing spaces and non-ASCII characters work.
- Missing mpv, unreadable files, and playback errors have understandable states.
- Relaunching retains the library.
- Quitting stops only the application’s owned playback process.

**Milestone 2 — everyday listening**

Add persistent playlist editing, reliable queue interaction, rescanning, listening-position restoration, responsive layouts, and keyboard help.

Verify multi-disc albums, compilations, duplicate album titles, missing tags, missing files, and playlist persistence.

**Milestone 3 — Kirlian character**

Add optional artwork, the final terminal styling, and ASCII animations.

Review the first two animation families before expanding them. Verify pause/resume, disabling animation, clipping, terminal resizing, and artwork fallback.

**Milestone 4 — optional facts and release preparation**

Add the facts integration and its setup flow. Test timeouts, stale responses, missing sources, and credential handling using controlled fixtures before making live requests.

Complete installation and playback checks on both macOS and Linux. Record which terminals were tested. Do not claim platform support solely from headless tests.

**11. Instructions for the coding agent**

Begin with **Milestone 1 only** and complete it through working playback.

Inspect the supplied directory before creating files. Preserve any existing work. Keep dependencies and code organization proportionate to this application.

Write meaningful tests around album grouping, queue behavior, text-input shortcuts, and playback event handling. Include a documented manual listening check; automated tests alone cannot establish playback quality.

At handoff, provide:

- The exact install and launch instructions.
- What works and any known limitations.
- Tests performed and platforms actually checked.
- A short manual walkthrough the owner can use to try the application.

Stop at that review point before adding optional features.

## Accepted refinement: filament and personalization (2026-10-13)

The owner selected the filament ribbon from the listening studies and approved
implementation with branding, appearance controls, and sharp native artwork.
The player now uses that layout. Local appearance choices are palette, motion,
character drawing, and header; preview must preserve playback and cancel cleanly.
Terminal compatibility uses native-image, rich-text, and basic-ornament fallbacks.
Real-terminal acceptance remains separate from protocol/unit checks; see
[terminal compatibility](terminals.md) and [testing](testing.md).
