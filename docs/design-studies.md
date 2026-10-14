# Listening interface studies

## Status: filament ribbon accepted and implemented

On 2026-10-13 the owner requested a more beautiful play bar, a recognizable
Kirlian logo, and mockups for setup and personalization. The reference material
includes the current terminal, the desktop website's waveform player, and the
Kirlian radial mark with its serif wordmark.

The owner selected the filament ribbon and requested its implementation with
branding, personalization, and sharp native covers. The running application now
uses that arrangement. The separate interactive study uses illustrative playback,
without audio or filesystem access. Its supplied logo reference remains in the
private conversation preview, outside this public repository.

## Visual direction

Keep the near-black surface, warm bone text, and muted aubergine accent. Use
alignment, space, and fewer competing labels to establish hierarchy. Put the
song first, artist second, and align the time consistently at the opposite edge.
Keep rarely used shortcuts in help; make the common actions discoverable.

Compare two arrangements:

| Study | Arrangement | Question for review |
| --- | --- | --- |
| Filament ribbon | A fine, three-row field spans the player under the song; a separate thin seek line remains legible. | Does the larger gesture feel calm over a whole album? |
| Quiet orbit | A small dot orbit sits beside the song, above a compact seek line. | Is this enough character with less occupied space? |

The ribbon is the accepted direction; the orbit remains an unimplemented alternative.
Neither pattern represents the audio signal. A waveform would require actual
audio-derived data; the website reference is a compositional reference only.

## Character rendering and artwork

The study compares ordinary ASCII marks with Unicode Braille patterns, whose
two-column, four-row dot cells allow finer curves than a full block per cell.
The latter is text-based drawing, but is not strictly ASCII. Font-dependent
appearance and spacing must be checked in the actual terminal before adoption.

Block-rendered album art is a separate compatibility path. Sharp covers are
confirmed in the standalone Ghostty screenshot; Herdr has shown block covers
but sharp covers there still require a confirmed Herdr session.
See the development record for the graphics setting and remaining lifecycle checks.

The owner then requested a terminal-native identity, replacing the serif image.
Both the sunburst and lowercase lettering are now hand-drawn as two rows of
Braille characters. The open center and radiating strokes echo the supplied mark;
the dotted line weight relates to the filament. No rasterized font or image is
used. Plain ASCII uses a punctuation emblem with monospace lettering; short windows use one line.
Drawn and Simple options preview in the existing appearance panel. The header
stays still and works independently of cover display or graphics support.

## Setup and personalization

Implemented setup: choose a music folder, listen with defaults, and open appearance with `p`. No account, provider key, or technical image-protocol
choice belongs in the main setup path. A preview must not imply that indexing
has happened before real files have been read.

Implemented appearance controls:

- Palette: aubergine, sage, or amber; keep neutral surfaces consistent.
- Motion: gentle, still, or off. Pause freezes motion; stopped playback does not
  show a pause indicator. Respect reduced-motion preferences where available.
- Character drawing: fine dots or plain ASCII.
- Wordmark: drawn or simple, using the selected character style.
- Keep a liked pattern; preserve the existing seed-based behavior.

Changes should preview immediately and preserve playback, queue, and selection.
The initial defaults must stand on their own without a customization step.

## Remaining in-terminal review

- Review both arrangements in motion and paused, including a full-song check.
- Check native artwork in Ghostty and configured Herdr, including resize,
  clearing, and monochrome behavior; retain a deliberate block fallback.
- Verify character alignment with the selected terminal font and at 80 × 24.
- Keep text entry isolated from global shortcuts and keep the player operable
  with all decorative motion off.
- Treat the browser study's narrow layout as preview accessibility, not proof
  that the terminal has passed its responsive checks.

References: [Ghostty features](https://ghostty.org/docs/features),
[Unicode Braille patterns](https://www.unicode.org/charts/PDF/U2800.pdf).

## 2026-10-13: spacing and hierarchy refinement

The owner requested a tighter interface after confirming visible artwork. The
running layout now brings the collection title and count together, removes the
redundant root breadcrumb, and uses one surface behind table rows. The selection
provides the focus accent; the sidebar stays quieter until it has keyboard focus.
The bottom has a single line for contextual keys and volume. Extra animation
commands remain in Help. The original three-row filament and cover dimensions
are preserved; unused metadata dividers and the permanent readiness line are gone.

## 2026-10-14: variety within the accepted ribbon

The owner confirmed that the latency work feels better and requested around 100
permutations. The ribbon now has ten motion families with ten named variations
each, from continuous threads and growing forms to sparse sparks and constellations.
Orbits here are drawn within the accepted ribbon; this does not switch the player
to the earlier compact-orbit layout alternative.

| Before | After | Why |
| --- | --- | --- |
| New songs mainly vary a single filament silhouette | 100 recipes across ten geometric families | Make changes perceptible while keeping a coherent visual language |
| Unbounded random seeds can feel similar in succession | A shared shuffle pool prefers a different family | Offer variety over a listening session |
| Saved patterns identified chiefly by hex seeds | Stable names for new recipes, old seeds preserved | Make favorites recognizable without changing existing saves |
| Three rows, album colors, capped drawing rate | Same dimensions, color ownership, and rate | Preserve the accepted layout and recent responsiveness |

The [catalog](patterns.md) describes every family and provides a generator for
previews taken from the real renderer. Static studies establish composition only;
the feel of an entire album still benefits from listening in the target terminal.
