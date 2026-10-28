# Contributing

This project is at its first playback milestone. Start with the
[specification](docs/specification.md) and the [development record](docs/development.md).
Keep changes small enough to try in a real terminal.

Document changes alongside the code:

- Update the README when installation, shortcuts, or visible behavior changes.
- Explain substantial decisions and tradeoffs in `docs/architecture.md`.
- Record what changed, what was checked, and what remains uncertain in
  `docs/development.md`. Use dates and reproducible commands.
- Keep planned behavior distinct from implemented and manually verified behavior.

Use generated audio in automated tests. Do not commit recordings, album artwork,
credentials, local databases, or personal filesystem paths. When reporting a
problem, include the OS, terminal, Python and mpv versions, steps, expected result,
and actual result. Replace private metadata and paths in logs.

## License

Kirlian Terminal is licensed under GPL-3.0-or-later (see `LICENSE`). By
contributing, you agree that your contribution is licensed under the same terms.
New source files start with `# SPDX-License-Identifier: GPL-3.0-or-later`
(`/* … */` in `.tcss`). Do not add dependencies whose licenses are incompatible
with GPL-3.0-or-later; record any new dependency in `docs/licensing.md`.

## Translations

Visible text goes through `kirlian_terminal.i18n`: `_("Whole sentence with {name}", name=value)`,
`n_("{n} song", "{n} songs", count)` when a count changes the wording, and `N_()` to
mark text defined before a language is set. The first argument must be a literal.
Never put tags, filenames, or provider text into the source string; pass them as values.
Catalogs are `src/kirlian_terminal/locales/<code>.json`, mapping English source to
translation. `uv run python scripts/i18n_catalog.py` reports missing, stale, and
mismatched-placeholder entries for every language (the test suite runs the same
check); `--template` writes the current sources with their locations to
`locales/_template.json` for translators (do not commit it).
