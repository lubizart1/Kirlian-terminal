# Kirlian Terminal

A small terminal music player for people who listen to albums.

Kirlian Terminal plays local music, keeps your place in the record, and is being
built as a standalone companion to Kirlian. Playback is offline. No account or API
key is required, and the player does not modify your music files or tags. Optional
song facts use your own API key for a provider you choose (Exa, OpenAI, Anthropic,
Perplexity, or Parallel) and are off until you turn them on.

**Status: local prototype with the filament listening interface.**
Includes background indexing, album/artist/song browsing, search, an active queue,
saved playlists, keyboard playback controls, local covers, a filament ribbon, the
Kirlian header, local appearance preferences, and optional sourced song facts.
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
| `/` | Search songs, albums, artists, and playlists |
| `Esc` | Leave search or go back |
| `Tab` / `Shift+Tab` | Change pane |
| `a` | Append selected song or album without interrupting playback |
| `+` | Add the selected song, album, or queue item to a playlist |
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
| `i` | Set up, change, or turn off song facts |
| `[` / `]` | Previous / next fact for the playing song |
| `o` | Open the shown fact's source in your browser |
| `q` | Quit and stop this player's audio |

The bottom row shows the current Enter and Space actions, pattern, help, quit,
and volume. Search and personalization stay in the header; Help lists the other
controls. Collection headings and counts share a row, and status messages appear
only when there is something to report.

Typing in search, the folder field, playlist names, or the API key field takes
priority over these shortcuts.
Search does not stop playback; Escape restores the previous view and selection.
Playing a search result starts its album queue at that song. Enter on a Queue
item jumps to it. `>` marks the current track; the highlighted row is your selection.

The player reads MP3, FLAC, M4A/AAC, Ogg Vorbis/Opus, and WAV candidates. Playback
depends on your installed mpv decoders and the file itself. Unreadable files are
summarized during scanning; playback failures appear in the status line. If a scan
finds no music, the status line says whether folders were permission-denied. On
macOS, the Music app's library inside `~/Music` is protected: allow your terminal
under System Settings › Privacy & Security › Files and Folders, or press `f` to
choose a different folder.

## Playlists

Press `+` on a song, album, or Queue item, then choose a playlist or
**+ New playlist…**. Open **Playlists** in the sidebar (or search for a playlist
by name) to see them all; the first row creates an empty one.

| Where | Key | Action |
| --- | --- | --- |
| Playlists list | `Enter` | Open a playlist, or create one from the first row |
| Playlists list | `e` / `d` | Rename / delete (asks first) |
| Playlists list | `a` | Append the whole playlist to the queue |
| Inside a playlist | `Enter` | Play the playlist in saved order from that song |
| Inside a playlist | `J` / `K` | Move the song down / up |
| Inside a playlist | `d` | Remove that entry |
| Inside a playlist | `e` | Rename |

A song can appear more than once on purpose. If a file goes missing, its entry
stays and is marked `[unavailable]`; playback skips it, and `d` removes it.
Deleting a playlist never touches your music files.

## Song facts

The side panel can show a short **Behind the record** note about the playing
song: who played on it, where it was recorded, or how it came together. Each fact
names its source, and only facts that match a page the provider's search actually
retrieved are shown. `[` / `]` step through up to three facts; `o` opens the source.

Facts are off by default and use your own API key with one of these providers:

| Provider | Get a key | Environment variable | What is called |
| --- | --- | --- | --- |
| Exa | [dashboard.exa.ai](https://dashboard.exa.ai) | `EXA_API_KEY` | `/answer` |
| OpenAI | [platform.openai.com](https://platform.openai.com/api-keys) | `OPENAI_API_KEY` | Responses API, `gpt-5.4-mini` with web search |
| Anthropic | [platform.claude.com](https://platform.claude.com) | `ANTHROPIC_API_KEY` | Messages API, `claude-haiku-4-5` with web search |
| Perplexity | [perplexity.ai](https://www.perplexity.ai/account/api) | `PERPLEXITY_API_KEY` | Agent API, `fast` effort |
| Parallel | [platform.parallel.ai](https://platform.parallel.ai) | `PARALLEL_API_KEY` | Responses API, `low` effort |

Each provider bills your account per request. To turn facts on, press `i`, choose a
provider, paste its key, and choose **Turn on** (saved in the system credential
store, such as the macOS Keychain) or **This session only**. Without a usable
credential store the key lasts for the session only. Each provider's key is stored
separately, so switching back does not require pasting it again. A key exported in
that provider's environment variable takes precedence; press `i` to turn facts on.
**Turn off** removes all saved keys. To try a different OpenAI or Anthropic model,
set `KIRLIAN_FACTS_MODEL` before launching.

Only the song title, artist, album, and year are sent to the chosen provider, two
seconds after a song starts. Audio, artwork, and file paths are never sent. Each
song is asked about once; answers, including "nothing found", are kept in the local
database and reused if you switch providers.
The card appears while the side panel shows the playing song's album, so it hides
below 110 columns. Timeouts, a rejected key, or a spent quota appear in the status
line and never interrupt playback.

While a request is open, the card shows the playing title as a beat: each syllable
is a hit (the first of each word accented, every digit its own hit), each gap
between words a rest, and a playhead walks the pattern. "Paris 1919" becomes
`● • · ● • • • ·`. It holds still under the Still or Off motion setting and stops
as soon as the answer, or an error, arrives.

### Checking your key

To try a provider and key outside the player, make one live request:

```sh
uv run kirlian --check-facts            # the provider chosen in the player
uv run kirlian --check-facts openai     # a specific provider
uv run kirlian --check-facts all        # every provider with a saved or exported key
uv run kirlian --check-facts exa --artist "Talk Talk" --title "New Grass" \
  --album "Laughing Stock" --year 1991
```

It uses the saved or exported key; if there is none, it asks for one without
echoing it and does not save it. The key is never printed. Output shows the
response time, how many pages the provider retrieved, and each proposed fact
marked ✓ (shown) or ✗ (its source was not a retrieved page). Provider error
messages, such as an unknown model, are printed as returned. Add
`--facts-report report.json` to keep the full response for inspection; the report
contains no key. The default song is John Cale's "Paris 1919". Each check is a
billed request.

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
the chosen folder, file availability, cover display choice, appearance preferences,
saved seeds, playlists, and fetched song facts in its own SQLite database. Song-facts
API keys are kept in the system credential store, never in that database:

- macOS: `~/Library/Application Support/kirlian-terminal/`
- Linux: `$XDG_DATA_HOME/kirlian-terminal/`, defaulting to `~/.local/share/kirlian-terminal/`

`--data-dir` overrides that location. This prototype selects one music root at a
time. Playback uses a private local socket and one owned mpv child process. There
are no accounts, analytics, or network services. The only network request is the
optional song-facts call to the provider you chose, described above.

## Current limits

- Listening-position restoration is not implemented.
- Relaunching retains the library, but clears the active queue and starts stopped.
- Album identity uses tags and release folders. Discs in `CD 1` / `Disc 2` style
  subfolders share the parent folder. Distinct editions with identical tags in one
  flat folder cannot reliably be separated. Unknown artists in untagged mixed
  folders also need better source organization for accurate grouping.
- Long titles are clipped in the table; the context pane provides more space on
  wider terminals. It hides below 110 columns, taking the fact card with it. The
  minimum target is 80 × 24.
- Song facts are tested against hand-written responses in each provider's documented
  format; no live request to any provider has been made in this repository's checks.
  Default models will age; `KIRLIAN_FACTS_MODEL` overrides them.
- Google Gemini is not offered: its grounding returns redirect links rather than
  the source pages, which the source check cannot match.
- Saved playlists live in the Playlists view, not as individual sidebar entries.
- Audio quality and gapless album transitions need a human listening check.

## Project notes

- [Product specification](docs/specification.md): supplied handoff and release boundaries.
- [Architecture and decisions](docs/architecture.md): why the project is organized this way.
- [Development record](docs/development.md): changes, evidence, and remaining work.
- [Listening interface studies](docs/design-studies.md): accepted play bar, branding, and personalization direction.
- [Testing and listening](docs/testing.md): automated checks and a manual walkthrough.
- [Contributing](CONTRIBUTING.md): development and documentation expectations.

The first milestone covers local indexing, album browsing, search, and playback.
The owner has since brought artwork, the filament ribbon, branding,
personalization, saved playlists, and optional sourced song facts forward.
Streaming, downloads, lyrics, cloud sync, and visual generation are outside this
release.

## License

Kirlian Terminal is free software under the GNU General Public License, version 3
or later (`GPL-3.0-or-later`); see [LICENSE](LICENSE). The player uses Mutagen
(GPL-2.0-or-later) to read tags. Dependency terms are summarized in the
[license review](docs/licensing.md).
