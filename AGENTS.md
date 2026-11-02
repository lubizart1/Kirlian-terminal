# Working on Kirlian Terminal

Guidance for anyone working on this repository with a coding agent. Contributors
can keep personal instructions in `AGENTS.local.md` (git-ignored); if that file
exists, read it too, and let it refine, not override, the rules below.

Read `README.md`, `docs/architecture.md`, and `docs/testing.md` before editing.

## Setup and checks

Requires Python 3.12+, [uv](https://docs.astral.sh/uv/), and mpv (ffmpeg as well
for the generated-format tests).

```sh
uv sync --locked
uv run ruff check .
uv run ruff format --check .
uv run python scripts/i18n_catalog.py   # every language covers every string
uv run pytest -q
uv build && packaging/render-install.sh # package and installer
```

CI (`.github/workflows/checks.yml`) runs the same on Ubuntu and macOS with Python
3.12–3.14, then installs the built package with `install.sh` on clean runners.
Keep it green; GitHub runners are slower than a laptop.

## Rules that protect listeners

- **Offline by default.** The only network request is the opt-in song and album
  notes call to the provider the listener chose. It sends title, artist, album,
  year, and language, never audio, artwork, file paths, or folder names, and never
  before notes are turned on. Store links only open the browser when chosen.
- **Never write to music files**, their tags, or their folders.
- **API keys** stay in the environment, the session, or the OS keychain; never in
  SQLite, logs, reports, or the repository.
- **Untrusted text.** Tags, filenames, theme files, and provider answers are
  untrusted: render them as plain text, strip control characters, and show a note
  only if its source URL is a page the provider's search actually retrieved.
- **The owned mpv process** manages playback and the queue. Derive state from its
  events; do not simulate playback in the UI. Stop only the process Kirlian started.

## Code conventions

- A small Python package: no services, plugins, or speculative abstractions.
- New source files start with `# SPDX-License-Identifier: GPL-3.0-or-later`.
- Every visible string goes through `kirlian_terminal.i18n` (`_`, `n_`, `N_`) with a
  literal first argument, and gets a translation in each `locales/*.json`.
- Colors come from `appearance.COLORS` and the `$k-*` stylesheet variables; never
  hard-code a color, or themes cannot reach it.
- Blocking work (scanning, SQLite, artwork, keychain, network) runs in workers or
  threads, never on the UI event loop.
- Anything that updates widgets from a worker, timer, or player event must cope
  with the screen being rebuilt (`app.rebuilding`) or already closed.
- Text input takes priority over navigation and playback shortcuts.
- Keep graphics and text fallbacks working: native images, blocks, ASCII, no color.

## Tests

- Use generated audio (`audio_factory`) and temporary folders; never real music,
  user paths, the network, or the real keychain (tests use an in-memory keyring).
- Wait for conditions, not time: `wait_for(pilot, lambda: ...)` and
  `wait_for(pilot, lambda: app.ready)` before the first key press. Fixed pauses
  pass on a fast machine and fail in CI.
- Test behavior a listener would notice (album identity and order, queue, input
  focus, playback events, saving), not wording or wiring. A bug fix comes with a
  test that fails without it.
- Passing tests do not establish audio quality or how a real terminal looks; list
  what still needs a human check under "Not yet verified" in `docs/testing.md`.

## Documentation

- Update the README when setup, keys, or visible behavior change.
- Record design decisions in `docs/architecture.md`.
- Describe changes and how they were checked in the commit message.
- Public files must not contain credentials, personal music, absolute user paths,
  or claims of support that nobody has checked.

The project is licensed under GPL-3.0-or-later; contributions are accepted under
the same license (see `CONTRIBUTING.md`).
