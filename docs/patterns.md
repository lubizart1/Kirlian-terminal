# Ribbon pattern catalog

The player has 100 local patterns: ten families, each with ten named variations.
They occupy the existing three-row ribbon and inherit the playing album's palette.
The shapes are decorative; they do not claim to measure the audio.

| Family | Character |
| --- | --- |
| Filaments | One wandering thread with fine strands beside it |
| Tides | Slow, overlapping swells |
| Braids | Two threads crossing and separating |
| Ripples | Nested, widening elliptical rings |
| Orbits | Open loops with small moving satellites |
| Fronds | Curved leaves growing from a fine stem |
| Mycelium | Branches and forks along a wandering root |
| Embers | Sparse drifting sparks with short trails |
| Seeds | Small floating forms turning in a slow current |
| Constellations | Loose clusters, dotted connections, and tiny changing stars |

Each family includes **Drift, Undercurrent, Glimmer, Breath, Current, Stillwater,
Weave, Dusk, Bloom, and Whisper**. The recipes vary pace, direction, spacing,
amplitude, density, and deterministic starting positions. These names identify
stable patterns; they are not generated labels for arbitrary random seeds.

## Choosing and keeping patterns

- Starting a song or pressing `x` draws another pattern. A session pool visits
  all 100 before refilling and prefers another family whenever one remains.
- `s` saves the current pattern locally. `S` cycles saved patterns from the start.
  Manual recall can revisit a favorite without waiting for the shuffle pool.
- Pause freezes the pattern. Resume continues its phase. Seeking changes the
  progress highlight, but does not reset the drawing or choose another pattern.
- `p` still controls gentle / still / off motion, dot / ASCII characters, and
  the interface palette. `v` toggles motion. The album controls ribbon colors.

Saved patterns persist; the shuffle pool and animation phase are session state.
Original version-1 filament and ripple seeds remain readable and reproduce their
original drawings. New catalog entries use version-2 identifiers. Nothing needs
to be migrated or erased.

## Preview and performance tools

Generate a static SVG from the actual renderer without opening any music:

```sh
uv run python scripts/preview_patterns.py --output .local/pattern-families.svg
uv run python scripts/preview_patterns.py --all --output .local/all-patterns.svg
uv run python scripts/preview_patterns.py --characters ascii --seconds 20
```

The preview uses a fixed illustrative palette, local fonts, and no external assets.
It is a sample of the drawing, not a screenshot proving rendering in a particular
terminal. `--all` includes all 100; the default shows Drift from each family.

Run `uv run python scripts/benchmark_patterns.py` to measure pure frame generation
at 76, 156, and 400 columns in both character modes. This excludes Textual layout,
terminal transport, and album artwork. Results depend on hardware and load.

The renderer caps width at 400 cells, stores only the current three rows, and draws
at the existing maximum of 10 frames per second. It does not cache 100 animation
sequences, read music, access the network, or request a screen layout per frame.
