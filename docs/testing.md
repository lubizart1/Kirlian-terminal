# Testing and listening

## Automated checks

From the repository root, with uv and mpv installed (also install the `ffmpeg`
command-line tool to run the optional generated-format checks):

```sh
uv sync --locked
uv run ruff check .
uv run ruff format --check .
uv run python scripts/i18n_catalog.py
uv run pytest -q
uv build
```

The tests generate their own audio in temporary folders. They do not use your
music library. mpv integration tests use a null audio output and skip if mpv is
missing; a run with these tests skipped does not verify the playback engine.
The format matrix additionally needs ffmpeg and covers MP3, FLAC, M4A, raw AAC,
Ogg Vorbis, Opus, and WAV. ffmpeg is a test-fixture tool, not an application dependency.

The suite covers release-folder separation, compilations, multi-disc numeric
ordering, missing tags, unreadable and missing files, persistence, no writes to
indexed audio, search and folder input focus, song-search queue semantics, and
background indexing. Integration checks exercise a real mpv process: selecting a
queue position, appending duplicates, pause, seek, volume, previous/next, natural
track transitions, errors, and cleanup that leaves an unrelated player running.

`.github/workflows/checks.yml` runs the same commands on every push to `main` and
every pull request: lint, formatting, and translation coverage once; the test suite
with real mpv and ffmpeg on Ubuntu and macOS with Python 3.12, 3.13, and 3.14; then a
build whose wheel is installed into a fresh environment and started. A workflow file
is not evidence that a run passed. Headless tests do not establish terminal or
audio-device support.

## Manual playback walkthrough

Use music you have the right to play. Do not commit it or its artwork.

1. Run `uv run kirlian --data-dir .local/listening-check`. This separate data
   directory lets you check onboarding without changing your regular library.
2. Enter a real music folder, including spaces or non-ASCII characters if possible.
   Watch albums appear and move around while indexing continues.
3. Open an album with Enter. Confirm disc/track order and durations, then play its
   first song. Check that the playing marker and selection are distinct.
4. Listen to the complete album. Pay particular attention to the transition
   between tracks that should be continuous. Record audible gaps, clicks, repeats,
   or missing starts. A working progress bar cannot establish this result.
5. Pause/resume with Space; seek with H/L; change volume with -/=; skip with n/N.
   Compare displayed state to what you hear.
6. Search with `/`. Type `a q n /` including the spaces. Music must keep playing,
   without skipping, changing volume, or quitting. Escape should restore the
   previous browser position.
7. Search for a song and play it. Confirm the queue is its album, starting at that
   song. Browse elsewhere, then append an album with `a`; playback must continue.
   Open Queue through the navigation pane and press Enter on an item to jump.
8. Resize to 80 × 24. The context pane should disappear, and browsing, durations,
   playback, search, and keyboard controls should remain usable. Try a wider size.
9. Quit with `q`. Verify this app's playback stops and any independent mpv process
   remains running. Relaunch using the same data directory: the library should
   load without a new scan. Playback-position restoration is a later milestone.
10. With disposable copies or generated fixtures, try a missing file, unreadable
    file, broken audio file, and a rescan with `r`. Check that failures are visible.

For every pass record: date, source revision or working-tree status, OS and
architecture, terminal and size, Python and mpv versions, audio device, formats,
album completeness, each action checked, and observed failures. Keep public notes
free of personal paths and private listening metadata.

## Not yet verified

Automated tests do not replace these checks. Remove an item once it has been checked.

- **Listening:** a full real-album pass for audio quality and gapless transitions;
  equalizer bands and presets, pitch shifting, and tape mode by ear.
- **Terminals:** Linux terminals and the Linux console; native covers while
  switching panes, resizing, and quitting in Herdr (see [terminals](terminals.md));
  CJK text width and font fallback; the 180 patterns in a real terminal.
- **Song notes:** live requests to providers other than Anthropic. Default model
  names will age.
- **macOS privacy:** whether granting folder access exposes downloaded
  (non-streaming) Music app files.
- **Translations:** drafted by AI, not yet reviewed by native speakers. Flagged:
  key names left in English inside sentences ("Pulsa space…"); the word chosen
  for "fallback" in each language; macOS settings paths written from memory;
  Korean particles after placeholders (이(가)); mixed gender in pt-BR "Reserva"
  descriptions; German "bewegen" used for both focus and reordering.
- **CI:** the workflows have not yet run on GitHub.


## Artwork and animation review

1. In a terminal at least 110 columns wide, select albums with embedded covers,
   folder covers, and no cover. Verify the image belongs to the selection and text
   remains usable in all three cases. Move quickly between records while loading.
2. Resize between 80 × 24, 120 × 36, and a wider view. Confirm columns fit, the
   context pane returns, and the fixed animation area never shifts other controls.
3. Play, pause, resume, and seek. The same seed stays through pause/seek; paused
   frames remain still. A new file, including replaying the same path, picks a new seed.
4. Try `x`, `v`, `s`, and `S`: remix, disable/enable, save, recall. Restart to check
   saved variations and the motion preference. None should change the queue.
5. Type those letters in search and the folder field. They must remain text.
6. Inspect both families over a whole song: quiet enough, recognizable, no flashing?
   This is an artistic review, separate from the deterministic generator tests.
7. For native Kitty/Sixel graphics, check clipping, resize, disappearance on narrow
   layouts, changing covers, and terminal cleanup on exit. These remain unverified.
8. In Ghostty, press `c` to compare the block cover with native
   rendering. If native is blank, press `c` again. The album, queue, and playback
   state should stay the same. Restart and check that the choice is remembered.
   Type `c` in search and verify it remains text. `--artwork blocks` overrides a
   saved native preference for one launch. With `NO_COLOR=1`, verify a grayscale
   cover in both modes without corrupting the native image identifiers.

## Filament and terminal compatibility

Use `p` while playing a track: change palette, select Still, switch characters, and
Cancel. Verify the same song, queue, selection, seed, and phase remain. Reopen it,
Use Save changes (or Ctrl+S), restart with the same data directory, and check
persistence. Reset is only a preview until saved. Confirm the unsaved-state label,
accent sample, and success message. A paused ribbon should stay still under Gentle;
its colors should continue to follow the playing album rather than the interface
palette. With NO_COLOR or a short window, scroll to the contextual explanation.
At 80 × 24, scroll through settings and reach every button using Tab. Escape must
close an expanded choice before it cancels the page. Type `p`, `c`, and `x` in search
and folder fields to verify they are text, not shortcuts.

Run with `--artwork auto`, `--artwork blocks`, and `--artwork off --characters ascii`.
In a known native-capable terminal, test `--artwork native` in color and NO_COLOR.
Watch the cover through browsing, preferences, resize, and exit; there must be
no orphaned or stale image. The logo is now character drawing in every mode;
check its Drawn/Simple, ASCII, and compact variants independently of cover support. Record the terminal/version and font.
See [the compatibility matrix](terminals.md); automated protocol output alone must
not be recorded as a visual pass for any emulator.

For native failures, use `uv run kirlian --check-artwork` after quitting the player.
Record the visible samples and printed report. Add
`--artwork-report .local/artwork-report.json` for a saved local report. Version 2
compares four direct formats, the player placeholder path, and blocks. Tests run
the command in an owned pseudo-terminal with simulated raw RGB/RGBA support and
an RGB-only variant, both rejecting PNG. Checks include correct error attribution,
cancellation, terminal-mode restoration, saved source fingerprints/version replies,
and no library creation or mpv dependency. These tests verify the diagnostic,
not actual emulator pixels.

Additional owned-PTY startup tests return `libghostty`, `ghostty 1.3.1`, or no
identity while reporting generic graphics support. Verify the automatic cover
choice, the explicit native override, cached queries, and restored
terminal modes. A generic embedded engine must not become a native visual pass
solely because its parser acknowledged an image.

The startup tests also run through simulated tmux DCS envelopes. The diagnostic
suite checks that image chunks, placements, and targeted deletion are wrapped,
placeholder cells remain plain terminal text, and pixels survive transmission.
This does not emulate tmux pane layout or certify a real multiplexer. Herdr
socket/pane environment keys are recorded as set/unset without their values.

Character-header integration checks cover all three artwork modes, resize from
120 × 36 to 80 × 24 and 80 × 36, nonoverlap with header controls, appearance
preview/cancel, ASCII drawing, and persistence of the Simple preference.

## Compact hierarchy review

At 80 × 24 and a wide window, check the single-row collection heading/count and
one-row playback hints/volume. Enter should say Open for a collection and Play
for a song; Space follows the observed playing/paused state. Long cell text uses
an ellipsis. Focus the sidebar and return to the table: focus should stay clear
without tinting the whole table. Search and personalization keep their own hints.

With no track loaded, there is no 0:00 / 0:00 readout or permanent Ready message.
Errors and operation results must still be visible. A selected album without a
track note has no stray rule beneath its caption. The character ribbon retains
its three rows, and the native artwork path and size are unchanged.
