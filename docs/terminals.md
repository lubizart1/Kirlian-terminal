# Terminal compatibility

The goal is the same music player across terminals, with decoration adapted to
capabilities. Native covers are an enhancement. Browsing, search, playback, queue,
and keyboard controls must remain usable without images, mouse input, or motion.

## Rendering levels

| Level | Intended rendering | Selection |
| --- | --- | --- |
| Native images | Sharp local covers, character wordmark, dot ribbon | Successful supported graphics probe, or `--artwork native` |
| Rich text | Character wordmark, dot ribbon, optional block covers | No usable native backend; `--artwork blocks` |
| Basic ornament | ASCII ribbon and playback marks, block covers | `--artwork blocks --characters ascii`; default for `TERM=linux` |

Artwork can be disabled explicitly with `--artwork off` in any terminal. Linux
itself does not limit artwork: Linux terminal apps may support native images,
while the bare virtual console uses character blocks by default.

Colors follow terminal color support. `NO_COLOR` preserves monochrome presentation;
Kitty image identifiers are exempt because their RGB values encode protocol data.
The ASCII override concerns Kirlian's ornament, not transliteration of music tags.
Textual still renders widget borders and controls using Unicode. A Linux virtual
console's font and locale therefore remain part of acceptance testing.

## Current expectations, not certification

| Terminal | Intended path | Evidence / remaining work |
| --- | --- | --- |
| Ghostty application | Native Kitty images, blocks as fallback | Owner's 2026-10-13 screenshot confirms sharp cover and the previous graphic wordmark together in the standalone app. The header now uses characters. Album switching, resize, and cleanup still need real-terminal visual checks. |
| Herdr 0.8.2 | Blocks by default; explicit native after host setup | Owner corrected the earlier host identification: this is Herdr, not Codex. Earlier screenshot confirms blocks. After graphics configuration, the owner reports success and supplies a sharp-cover screenshot; the final image does not include host identity. Dynamic pane switching, resize, and cleanup remain unverified. |
| Other unidentified libghostty hosts | Automatic block covers and character logo | Conservative selection for the generic library identity. `--artwork native` remains an explicit override for hosts with image rendering. |
| Kitty | Native Kitty images | Protocol author and supported upstream renderer. Real Kirlian session still needs a platform/version receipt. |
| macOS Terminal.app | Text fallback | Use blocks or no artwork. Verify font coverage, color mapping, focus, and resize in the actual application. |
| Warp | Text fallback automatically | Warp advertises images, but textual-image documents missing Unicode placements. Recheck native support against specific future versions. |
| Linux desktop terminals | Detected Kitty/Sixel or text | Capabilities vary by terminal, build, and settings. Linux CI is not visual terminal coverage. |
| Linux virtual console | Block artwork, ASCII ornament | TERM=linux selects these defaults. Real console, Unicode borders, block glyphs, fonts, audio permissions, and keyboard behavior still need testing. |
| tmux | Native through configured passthrough, or blocks | Image transport and identity queries tested through simulated DCS envelopes; no real tmux visual receipt yet. See setup below. |
| SSH / screen / other multiplexers | Start with blocks; native only after verification | A host may strip image sequences or alter colors. Do not infer support from the outer terminal name. Audio plays on the machine running mpv. |

The application probes before Textual takes over input. A successful generic image
probe does not prove support for every image-placement feature. Never advertise
universal sharp artwork: a terminal without a graphics protocol cannot display it.
A deliberate text layout should still look complete.

For a blank native cover, first press `c`. If blocks appear, decoding has succeeded
and the failure is in native display. Quit and run `uv run kirlian --check-artwork`
in the same terminal session (at least 80 × 24). The version 2 check shows:

| Sample | Image path |
| --- | --- |
| A | Uncompressed RGB, direct placement |
| B | Uncompressed RGBA, direct placement |
| C | Compressed RGBA, direct placement using the player's pixel sender |
| D | PNG, direct placement |
| E | Player's compressed RGBA and Unicode placeholders, outside Textual |
| F | Colored blocks |

Enter the visible letters and retain the printed report. Optionally add
`--artwork-report .local/artwork-report.json` to save replies, the observation,
dependency versions, and source fingerprints locally. The terminal version query
asks the running session itself; installed app metadata can differ. No reply is
recorded as unknown, not as a version or support inference.

If C and E work but the player is blank, investigate Textual's output and redraw
lifecycle. If C works but E does not, investigate placeholder handling. If A/B work
but C does not, investigate compression. If only F works, investigate transmission
replies and the terminal connection. `OK` acknowledges a command; it is not
evidence that the image was painted. Earlier three-sample checks used different
letters and, initially, PNG; keep their reports distinct from version 2.

The observed version-2 result was **F only**, with A/B/C/E acknowledged `OK`, D
rejected as `EINVAL: unsupported format`, and the live version reply `libghostty`.
The loaded source hashes matched the checkout. This isolates a native display
failure in the responding embedded host; it does not establish failure in the
standalone Ghostty app. Environment values `TERM_PROGRAM=ghostty` and
`TERM_PROGRAM_VERSION=1.3.1` are not sufficient to distinguish the two.

The generic `libghostty` response is the library's default when a host does not
provide its own version callback. Its PNG decoder is also optional. Kirlian now
asks the live terminal identity before selecting a Kitty backend and uses a
conservative automatic fallback for this generic identity. A missing identity
reply does not disable an otherwise supported renderer. Use `--artwork auto`
when a saved native override would otherwise bypass the automatic selection.

The owner subsequently supplied two labeled screenshots on 2026-10-13: the
standalone Ghostty app displays a sharp cover and the previous graphic wordmark;
the second view displays the same selected album with a block cover and character
wordmark. The owner subsequently corrected its identification to **Herdr**, not
Codex. Both are idle, wide-window views. They confirm visible fallback artwork in
Herdr, but do not resolve native images there. Dynamic album changes, resizing,
and exit cleanup still require real-terminal checks. The current header is
character drawing in every terminal and no longer uses an image protocol.

## Multiplexers

Herdr and tmux are separate implementations. Both the multiplexer and outer
terminal must support the image path; a Ghostty environment variable alone
cannot establish that. Character branding and block covers do not need native
graphics support.

### Herdr

The tested installation has client and server **0.8.2**. Its own
`herdr --default-config` declares Kitty graphics disabled by default under
`[experimental]`. In `~/.config/herdr/config.toml`, that version uses:

```toml
[experimental]
kitty_graphics = true
```

Merge the key into an existing section rather than duplicating a TOML table.
The local development installation was backed up, updated, and reloaded with
`herdr server reload-config`; the server reported `applied` with no diagnostics.
No server, client, or running pane was stopped. Detach and reattach the client
for graphics capability negotiation, then launch:

```sh
uv run kirlian --artwork native
```

The explicit flag matters: Kirlian still conservatively selects blocks for a
generic `libghostty` identity, even after the host enables graphics. If the image
remains blank, `c` restores blocks. Do not stop a shared server just to test this.
The current [Herdr documentation](https://herdr.dev/docs/configuration/#kitty-graphics)
uses `[terminal] kitty_graphics` and documents newer defaults; check the installed
version's generated configuration instead of assuming that example fits 0.8.2.
The owner initially reported a sharp cover but corrected that observation: it
was not Herdr. Later they reported “works!” and supplied a new screenshot with
a sharp album cover and the smaller character header. This confirms native
visibility in that session after the setup work. The final screenshot does not
show host identity or establish the exact client reattachment steps. No shared
server was restarted. Pane switching, resize, and cleanup remain unverified.

### tmux

For tmux 3.3 or newer, enable passthrough in the tmux configuration:

```tmux
set -g allow-passthrough on
```

This forwards specially wrapped escape sequences to the outer terminal.
Kirlian's pinned image dependency already applies the tmux envelope, including
ESC doubling, to native image chunks, placements, and deletion commands when
`TMUX` is set. Kirlian's runtime identity query and diagnostic identity query
use the same wrapper. No fake `TMUX` variable is needed for Herdr.
See the [tmux passthrough FAQ](https://github.com/tmux/tmux/wiki/FAQ#what-is-the-passthrough-escape-sequence-and-how-do-i-use-it).

Owned-PTY tests emulate this envelope and replies, check decoded pixels and
cleanup, and preserve plain placeholder cells. There is no tmux binary installed
in the current development environment; these are transport checks, not a real
tmux rendering pass. Pane placement, splitting, resizing, scrolling, multiple
clients, and nested multiplexers remain separate acceptance work.

## Acceptance per terminal version

Record OS, terminal/version, font, locale, color mode, and direct versus multiplexed
session. Check 80 × 24 and a wide window; resize while playing; browse rapidly;
open and cancel preferences; type shortcut letters in inputs; pause, seek, append,
and quit. Native checks must include album changes, monochrome, clipping, resize, and
cleanup after exit. In a multiplexer, switch tabs/panes, split and resize panes,
and verify covers never remain over an unrelated pane. Check the character
header in both Drawn and Simple modes, plus its ASCII and compact variants. Test with images and motion
off too. A passing synthetic protocol check is useful but is not a screenshot or
a human listening receipt.

## Sources checked 2026-10-13

- [Ghostty features](https://ghostty.org/docs/features)
- [Kitty graphics and capability queries](https://sw.kovidgoyal.net/kitty/graphics-protocol/)
- [Warp image support](https://docs.warp.dev/terminal/more-features/files-and-links)
- [textual-image compatibility and Warp limitation](https://github.com/lnqs/textual-image#supported-terminals)
- [libghostty default identity callback](https://github.com/ghostty-org/ghostty/blob/main/src/terminal/c/terminal.zig)
- [Ghostty application's version response](https://github.com/ghostty-org/ghostty/blob/main/src/termio/stream_handler.zig)
- [Optional libghostty PNG decoding](https://github.com/ghostty-org/ghostty/blob/main/src/terminal/kitty/graphics_image.zig)

- [Herdr Kitty graphics configuration](https://herdr.dev/docs/configuration/#kitty-graphics)
- [tmux passthrough FAQ](https://github.com/tmux/tmux/wiki/FAQ#what-is-the-passthrough-escape-sequence-and-how-do-i-use-it)
