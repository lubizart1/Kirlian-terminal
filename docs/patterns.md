# Ribbon pattern catalog

The player has 100 local patterns: ten families, each with ten named variations.
They occupy the existing three-row ribbon and inherit the playing album's palette.
While a song plays, each family answers one part of the measured music (below);
without measurements, every pattern draws exactly its saved shape.

| Family | Character | Answers |
| --- | --- | --- |
| Filaments | One wandering thread with fine strands beside it | Mids lift the thread; treble adds strands |
| Tides | Slow, overlapping swells | Swells rise with the bass |
| Braids | Two threads crossing and separating | Loud passages pull them apart |
| Ripples | Nested, widening elliptical rings | Each hit pushes the rings outward |
| Orbits | Open loops with small moving satellites | Loops widen with bass; hits nudge satellites |
| Fronds | Curved leaves growing from a fine stem | Leaves reach further when loud |
| Mycelium | Branches and forks along a wandering root | Branches reach further when loud |
| Embers | Sparse drifting sparks with short trails | More sparks when loud; a burst on hits |
| Seeds | Small floating forms turning in a slow current | Swell with bass; turn with mids |
| Constellations | Loose clusters, dotted connections, and tiny changing stars | Cymbals and treble make stars flare |

Each family includes **Drift, Undercurrent, Glimmer, Breath, Current, Stillwater,
Weave, Dusk, Bloom, and Whisper**. The recipes vary pace, direction, spacing,
amplitude, density, and deterministic starting positions. These names identify
stable patterns; they are not generated labels for arbitrary random seeds.

## Choosing and keeping patterns

- Starting a song or pressing `x` draws another pattern. The old one dissolves
  into it dot by dot over 0.7 s, and the new pattern's name appears on the ribbon,
  holds, then scatters (about 1.8 s in all). Still and Off motion skip this. A session pool visits
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

## Depth and color

Each pattern marks its main stroke and its fine detail (side strands, outer rings,
orbit paths, leaf veins, ember tails, constellation lines). Fine detail is drawn
closer to the background color, so the main thread reads first. Album colors
blend across every character rather than in four-character blocks.
