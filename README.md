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
| `w` | Open or close the amp: level meters, equalizer, balance, ReplayGain |
| `s` / `S` | Save the current animation / cycle through saved animations |
| `c` | Switch cover display between terminal graphics and compatible blocks; remembered |
| `f` / `r` | Choose folder / rescan |
| `p` | Preview and save appearance preferences |
| `?` | Keyboard help |
| `i` | Song-notes settings: keys, provider order and fallbacks, models, on/off |
| `[` / `]` | Previous / next note for the playing song |
| `o` | Open the shown note's source in your browser |
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

## Song notes

The side panel can show short **Behind the record** notes about the playing song,
in the spirit of good liner notes or Genius annotations: what it is about, what a
lyric refers to, the circumstances it was written in, or a sound and why it is
there. Credits and studio lists are avoided unless there is a story in them.

Each note is one of two kinds, shown on the card:

- **Story**: something a source states. The card shows `Source: …`.
- **Reading**: an interpretation the model draws by connecting what sources say,
  phrased as a reading. The card shows `A reading, drawing on …`.

Either way, a note is shown only if its source is a page the provider's search
actually retrieved. The card names the source site, its year when stated, and
which provider answered. `[` / `]` step through up to three notes; `o` opens the
source.

Notes are off by default and use your own API keys:

| Provider | Get a key | Environment variable | What is called |
| --- | --- | --- | --- |
| Anthropic | [platform.claude.com](https://platform.claude.com) | `ANTHROPIC_API_KEY` | Messages API with web search; default `claude-sonnet-5-5` |
| OpenAI | [platform.openai.com](https://platform.openai.com/api-keys) | `OPENAI_API_KEY` | Responses API with web search; default `gpt-5.4-mini` |
| Exa | [dashboard.exa.ai](https://dashboard.exa.ai) | `EXA_API_KEY` | `/answer` |
| Perplexity | [perplexity.ai](https://www.perplexity.ai/account/api) | `PERPLEXITY_API_KEY` | Agent API, `fast` effort |
| Parallel | [platform.parallel.ai](https://platform.parallel.ai) | `PARALLEL_API_KEY` | Responses API, `low` effort |

Each provider bills your account per request. Press `i` for the song-notes
settings. Providers are listed in the order they are asked: the **Primary** first,
then **Fallback 1**, **Fallback 2**, and so on, then those not used. Moving a
provider moves its row. The line under the table explains the selected provider
(its role, and which model writes its notes) and shows only the keys that apply:

| Key | Action |
| --- | --- |
| `Enter` | Add or replace (rotate) the provider's key: **Save to keychain** or **This session only** |
| `Space` | Use the provider as the last fallback, or stop using it |
| `1`–`5` | Put it at that position; `1` makes it the primary |
| `K` / `J` (or Shift+↑ / Shift+↓) | Move it up or down |
| `m` | Choose the model that writes the notes (Anthropic and OpenAI), from a short list with what to expect, or any other model name |
| `d` | Remove its saved key |
| `t` | Turn notes on or off; keys are kept |
| `Esc` | Close and apply to the playing song |

The first provider in the order is asked first. The others are fallbacks, asked
only when an earlier one fails (rejected key, quota, timeout, error); the status
line says which failed. A key exported in a provider's environment variable takes
precedence over a saved one; unset it in your shell to stop using it. Without a
usable system credential store, saved keys last for the session only.

Only the song title, artist, album, year, and the language to write in are sent, two
seconds after a song
starts. Audio, artwork, and file paths are never sent. Each provider is asked about
each song once; answers, including "nothing found", are kept locally per provider,
so reordering providers lets you compare them on songs you have already heard.
The card appears while the side panel shows the playing song's album, so it hides
below 110 columns. Failures appear in the status line and never interrupt playback.

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
uv run kirlian --check-facts anthropic --model claude-opus-5-5
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

## The amp

Press `w` for a Winamp-style amp above the ribbon. It shows the playing file's
codec, bitrate, sample rate, and channels; live left/right level meters with peak
marks that hold for a second (`CLIP` when a peak reaches full scale); a ten-band
equalizer (31 Hz to 16 kHz, ±12 dB) with a preamp; a balance slider; and
ReplayGain. While the amp has focus:

| Key | Action |
| --- | --- |
| `←` / `→` (or `h` / `l`) | Choose the preamp, a band, or balance |
| `↑` / `↓` (or `k` / `j`) | Raise or lower it by 1 dB (balance by 10%) |
| `0` | Reset the selected slider |
| `e` | Equalizer on / off |
| `,` / `.` | Previous / next preset: Flat, Bass, Rock, Pop, Jazz, Classical, Dance, Vocal, Treble |
| `g` | ReplayGain: off, track, album |
| `w` or `Esc` | Close the amp |

Moving a slider turns the equalizer on. When it is off, its filters are removed,
so you hear the file exactly as before. Boosting bands can clip; lower the preamp
if `CLIP` appears. ReplayGain uses loudness tags already in your files and does
nothing for files without them. The equalizer, preset, balance, ReplayGain, and
whether the amp is open are remembered. Short windows show the equalizer as a
single row of bars. Everything runs inside mpv; your files are never changed.

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

The header is one line of ordinary terminal type: a spark (`✺`) and **kirlian**
in bold, matching the album-view mock. It needs no image support or custom font
and looks the same at every window size. Plain ASCII uses `*`.

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

The ribbon now moves with the music: it speeds up in loud passages and slows in
quiet ones, brightens when the sound is bright, and flashes along its length on
hits. These come from levels mpv measures as it plays, not from guesses; the
pattern itself still comes from the catalog. With Still or Off motion the ribbon
does not react.

## Language

The interface is available in English, Español, Français, Deutsch, Italiano,
Português (Brasil), 日本語, 한국어, and 简体中文. By default it follows your system
locale (`LC_ALL`, `LC_MESSAGES`, or `LANG`); other locales, including Traditional
Chinese, use English. Choose a language under `p` › **Language** and save: the screen
switches right away, and the music, queue, and open album stay as they were. Song notes are requested in the same language, with titles,
names, and quoted lyrics kept in the original. Album, artist, and song names always
appear exactly as tagged. Key names (`enter`, `space`, `esc`) stay in English, as do
the command-line options and `--check-facts` output.

The translations were written with AI assistance and have not yet been reviewed by
native speakers. Corrections are welcome; see [Contributing](CONTRIBUTING.md).

## Make it yours

Press `p` to preview aubergine, sage, or amber for the interface; gentle, still, or no motion; fine
dots or plain ASCII for the ribbon and header; and the interface language. The current
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
saved seeds, playlists, song-notes settings, and fetched notes in its own SQLite
database. Song-notes API keys are kept in the system credential store, never there:

- macOS: `~/Library/Application Support/kirlian-terminal/`
- Linux: `$XDG_DATA_HOME/kirlian-terminal/`, defaulting to `~/.local/share/kirlian-terminal/`

`--data-dir` overrides that location. This prototype selects one music root at a
time. Playback uses a private local socket and one owned mpv child process. There
are no accounts, analytics, or network services. The only network request is the
optional song-notes call to the providers you chose, described above.

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
- Notes were checked live with Anthropic only (one song, see the development
  record). The other providers are tested against hand-written responses in their
  documented formats. Default models will age; change them with `m` in settings.
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
