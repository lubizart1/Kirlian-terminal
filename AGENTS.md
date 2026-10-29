# Working on Kirlian Terminal

Read `README.md`, `docs/architecture.md`, and `docs/testing.md` before editing.
Private notes and old diaries live in the git-ignored `notes/` folder; never commit them.
Work in this repository independently of the other Kirlian application.

- Current authorized scope: local playback, the supplied visual mock, local artwork,
  the accepted filament ribbon, branding, local personalization, saved playlists,
  and opt-in song facts through a provider the listener chooses (Exa, OpenAI,
  Anthropic, Perplexity, Parallel). Listening-position restoration is still
  deferred. Maintain deliberate graphics and text fallbacks; terminal protocol
  checks are not real-terminal visual certification.
- Keep local playback offline. The only permitted network call is the opt-in facts
  request to the chosen provider, which sends title, artist, album, year, and language only,
  never audio, artwork, or paths, and never runs before the listener turns facts
  on. Only show facts whose source URL the provider's search actually retrieved. Keep API
  keys out of SQLite, logs, and the repository. Never write to music files,
  tags, or their folder organization. Treat tags, filenames, and provider text as
  untrusted text.
- Let the owned mpv process manage playback and its playlist. Derive playback state
  from mpv events; do not simulate it in the UI. Stop only the owned process.
- Text input takes priority over navigation and playback shortcuts.
- Keep filesystem scanning and other blocking work off the UI event loop.
- Prefer a small Python package over services, plugins, or speculative abstractions.
- Update the README for changed setup or behavior. Record meaningful design
  decisions in `docs/architecture.md` and keep the "Not yet verified" list in
  `docs/testing.md` current, in the same change as the code. Describe changes and
  checks in the commit message; there is no separate diary.
- Test album identity/order, queue behavior, input focus, and playback events.
  Record manual listening separately; passing tests does not establish audio quality.
- Public artifacts must not contain credentials, personal music, absolute user
  paths, private Kirlian internals, or claims of unverified platform support.
- The project is GPL-3.0-or-later. Do not publish a package or expand to later
  milestones without the owner's request.
