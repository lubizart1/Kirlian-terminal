# Working on Kirlian Terminal

Read `README.md`, `docs/specification.md`, and `docs/development.md` before editing.
Work in this repository independently of the other Kirlian application.

- Current authorized scope: local playback, the supplied visual mock, local artwork,
  the accepted filament ribbon, branding, and local personalization. Saved
  playlists and facts are still deferred. Maintain deliberate graphics and text
  fallbacks; terminal protocol checks are not real-terminal visual certification.
- Keep local playback offline and free of API calls. Never write to music files,
  tags, or their folder organization. Treat tags and filenames as untrusted text.
- Let the owned mpv process manage playback and its playlist. Derive playback state
  from mpv events; do not simulate it in the UI. Stop only the owned process.
- Text input takes priority over navigation and playback shortcuts.
- Keep filesystem scanning and other blocking work off the UI event loop.
- Prefer a small Python package over services, plugins, or speculative abstractions.
- Update the README for changed setup or behavior. Record meaningful design
  decisions in `docs/architecture.md` and changes, checks, limitations, and open
  questions in `docs/development.md` in the same change as the code.
- Test album identity/order, queue behavior, input focus, and playback events.
  Record manual listening separately; passing tests does not establish audio quality.
- Public artifacts must not contain credentials, personal music, absolute user
  paths, private Kirlian internals, or claims of unverified platform support.
- Do not silently select a license, publish a package, or expand to later milestones.
