# License

Kirlian Terminal is free software, licensed under the GNU General Public License,
version 3 or (at your option) any later version. The SPDX identifier is
`GPL-3.0-or-later`.

| Where | What it says |
| --- | --- |
| `LICENSE` | Full GPL version 3 text |
| `pyproject.toml` | `license = "GPL-3.0-or-later"`, `license-files = ["LICENSE"]` |
| Built packages | `License-Expression: GPL-3.0-or-later` and the bundled `LICENSE` |
| Source files | `SPDX-License-Identifier: GPL-3.0-or-later` header |
| `kirlian --version` | Version followed by the license name |
| README, CONTRIBUTING | License section and contribution terms |

In practice: anyone may run, study, modify, and share the player, including
commercially. Anyone who distributes a modified version must offer its source
under the same license. Running it privately carries no obligations. Contributions
are accepted under the same license.

## Why GPL

The player reads tags and embedded covers with Mutagen, which is
GPL-2.0-or-later. A GPL license keeps the project and that dependency consistent.
On 2026-10-26 the owner chose GPL-3.0-or-later over an earlier MIT direction and
decided to keep Mutagen: it covers every format the player supports, it is the
reader used by Quod Libet and (through `mediafile`) beets, and the player only
reads files, so a replacement would add parsing risk without a listener-visible
benefit. Replacing the tag reader is not planned.

## Dependencies

| Component | Installed version | Declared license | Role |
| --- | --- | --- | --- |
| Mutagen | 1.48.1 | GPL-2.0-or-later | Tag and embedded-cover reader |
| Textual | 8.2.8 | MIT | Terminal interface |
| Pillow | 13.0.0 | MIT-CMU | Image decoding and resizing |
| textual-image | 0.14.1 | LGPL-3.0-or-later | Terminal graphics and character-cell image rendering |
| platformdirs | 4.13.0 | MIT | Application data location |
| keyring | 25.7.0 | MIT | Optional song-facts API keys in the system credential store |
| mpv | External installation | Depends on build; see mpv's license | Separate playback process |

The MIT, MIT-CMU, and LGPL-3.0-or-later components are compatible with
distribution under GPL-3.0-or-later. This table lists direct dependencies, not a
full distribution audit; transitive dependencies and any bundled binaries need
their notices checked for whatever packaging format is eventually published.
textual-image is used unmodified, and its LGPL notice must remain visible in a
distribution.

mpv runs as an independently installed program through its normal JSON IPC. We do
not bundle its binary. A future bundled release requires a separate review of the
exact mpv/FFmpeg build and its redistribution terms.

Song-facts providers (Exa, OpenAI, Anthropic, Perplexity, Parallel) are external
services reached over HTTPS with the listener's own key. Their terms govern that
use; no provider code is included.

## What the license does not cover

Music and cover art read from the listener's folder are not repository assets and
are not covered by the code license. Do not commit test collections or their
artwork; local verification screenshots are ignored for the same reason. Facts
text returned by a provider belongs to its sources and is shown with attribution.

The header is a Unicode spark and the name set in the listener's terminal font;
no font binary or font-derived graphic is distributed. The serif wordmark image
(Canela-derived) is not part of the repository. The Kirlian name and brand identity are
separate from the code license: the GPL grants rights to the code, not to the
name.

## References

- [GNU GPL version 3](https://www.gnu.org/licenses/gpl-3.0.html)
- [GNU licensing FAQ](https://www.gnu.org/licenses/gpl-faq.html)
- [Mutagen's declared license](https://github.com/quodlibet/mutagen/blob/main/pyproject.toml)
- [LGPL version 3](https://www.gnu.org/licenses/lgpl-3.0.html)
- [textual-image package and license declaration](https://pypi.org/project/textual-image/)
- [Pillow license](https://pillow.readthedocs.io/en/stable/about.html#license)
- [mpv copyright and build conditions](https://github.com/mpv-player/mpv/blob/master/Copyright)
