# License review — pending

The owner confirmed MIT as the intended direction. No project license has been applied yet. Local development
can continue while the distribution decision is resolved.

MIT permits reuse, modification, and redistribution, including commercial and
closed-source derivatives, while preserving copyright and license notices.
GPL also permits commercial use, but distributing a combined or modified GPL
application generally carries corresponding source and GPL licensing obligations.
A public repository and an open-source license are separate decisions.

## Dependencies currently selected

| Component | Installed version | Declared license | Role |
| --- | --- | --- | --- |
| Mutagen | 1.48.1 | GPL-2.0-or-later | Imported metadata and embedded-cover reader |
| Textual | 8.2.8 | MIT | Terminal interface |
| Pillow | 12.3.0 | MIT-CMU | Image decoding and resizing |
| textual-image | 0.14.1 | LGPL-3.0-or-later | Terminal graphics and character-cell image rendering |
| platformdirs | 4.13.0 | MIT | Application data location |
| mpv | External installation | Depends on build; see mpv's license | Separate playback process |

This table records direct dependencies, not a completed distribution audit.
Transitive dependencies and bundled binary components also need their notices
checked for whatever packaging format is eventually published.

The current Python application imports Mutagen directly. Putting MIT on our own
files does not eliminate obligations for a distributed combined application that
uses GPL code. If MIT is the intended distribution direction, first evaluate a
permissively licensed metadata/cover reader and verify format/tag compatibility.
Retaining Mutagen and choosing an appropriate GPL license is the other direction.
No metadata replacement has been selected or implemented.

LGPL has different conditions from GPL: it permits use by differently licensed
applications when its requirements are met, including library notices, source
availability for the LGPL component, and users' ability to modify or replace it.
A normal replaceable Python dependency and a frozen bundled executable may need
different packaging treatment. textual-image is used unmodified; its LGPL license
must remain visible in a future distribution review.

mpv runs as an independently installed program through its normal JSON IPC. We do
not bundle its binary. Any future bundled release requires a separate review of
the exact mpv/FFmpeg build and their redistribution terms.

Music and cover art read from the listener's folder are not repository assets and
are not covered by a future code license. Do not commit test collections or their
artwork. Local verification screenshots are ignored for the same reason.

## References

- [MIT terms](https://choosealicense.com/licenses/mit/)
- [Mutagen's declared license](https://github.com/quodlibet/mutagen/blob/main/pyproject.toml)
- [GNU licensing FAQ](https://www.gnu.org/licenses/gpl-faq.html)
- [LGPL version 3](https://www.gnu.org/licenses/lgpl-3.0.html)
- [textual-image package and license declaration](https://pypi.org/project/textual-image/)
- [Pillow license](https://pillow.readthedocs.io/en/stable/about.html#license)
- [mpv copyright and build conditions](https://github.com/mpv-player/mpv/blob/master/Copyright)


## MIT reader candidate: TinyTag

[TinyTag](https://github.com/tinytag/tinytag) is a read-only, pure-Python MIT library
with support for ID3/MP3, MP4/M4A, FLAC, Ogg Vorbis/Opus, and WAV, including embedded
images. On 2026-10-13 a temporary environment with TinyTag 2.3.2 read the same local
65-track MP3/M4A collection used for playback checks. Titles, artists, albums,
album artists (with the current fallback), track/disc numbers, and years matched
our current reader. All 62 available embedded covers had identical image bytes.
The largest duration difference was approximately 0.073 seconds.

This is an encouraging compatibility sample, not a replacement implementation.
Before switching: verify compilations without an album-artist tag, multi-disc
ordering, missing/invalid tags, generated fixtures for every supported format,
raw AAC fallback behavior, and cover selection when several images are embedded.
The comparison did not modify the runtime dependency list or music files.

A custom reader would not require C or Rust, but would require binary-format
parsing, encoding/version handling, input bounds, and substantial compatibility
tests. A small application-owned adapter around an existing permissive parser is
the preferred candidate approach; a full Mutagen replacement is outside scope.


## Required coverage for a replacement

On 2026-10-13 the owner clarified that the target is support for every Kirlian
Terminal format. A smaller, read-only metadata interface must not reduce that
format coverage. The current format contract is MP3, FLAC, M4A/AAC, Ogg Vorbis,
Ogg Opus, and WAV, including separate raw `.aac` files. M4A is a container: the
replacement checks should include both AAC and ALAC audio within it.

For every format, acceptance requires:

- Discovery, indexing, and playback through the owned mpv process.
- Reading title, artist, album, album artist, track/disc numbers, and year where
  present, with explicit fallbacks for absent or unsupported tags.
- Correct album grouping, compilation handling, and numerical track/disc order.
- Embedded cover extraction where available, plus the existing folder fallback.
- Sensible duration handling, including documented estimates or unknown duration
  before playback; the UI must use the observed player state while playing.
- Safe behavior for missing tags, unusual text encodings, malformed input, and
  missing files, without writing to music files or blocking the interface.

Mutagen's editing, tag deletion, ID3 version conversion, and low-level Ogg stream
manipulation are broader than the player requires. Omitting those operations is
compatible with full coverage of the player's promised formats.

Current evidence is partial: the existing engine suite decodes generated examples
of seven format/codec combinations; the TinyTag comparison covers real MP3/M4A
files only. Neither establishes complete replacement metadata/artwork coverage.
In particular, the generated M4A fixture currently uses AAC, not ALAC, and TinyTag's
published format list does not establish standalone raw AAC support. These remain
explicit acceptance checks, not reasons to remove a format from scope.

References: [Mutagen API](https://mutagen.readthedocs.io/en/latest/api/index.html),
[Mutagen AAC behavior](https://mutagen.readthedocs.io/en/latest/api/aac.html),
[TinyTag formats](https://github.com/tinytag/tinytag#features).

## Terminal character branding

The header now uses original hand-drawn character strokes for the sunburst and
lowercase lettering. The earlier Canela-derived SVG and PNG are no longer packaged
or used. No font binary or font-derived graphic is distributed with the header.
Brand identity rights remain separate from the intended code license. This change
does not resolve or change the Mutagen/textual-image dependency review above.
