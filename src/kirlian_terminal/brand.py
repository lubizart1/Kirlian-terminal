# SPDX-License-Identifier: GPL-3.0-or-later
"""The header mark: a spark glyph and the name in the terminal's own type.

U+273A (sixteen-pointed asterisk) echoes the radial mark. It has no emoji
presentation, unlike U+2733, so terminals do not swap in a color emoji.
"""

from rich.text import Text
from textual.widgets import Static

from .appearance import INK

SPARK = "✺"
ASCII_SPARK = "*"
NAME = "kirlian"


def mark(ascii: bool = False) -> Text:
    return Text.assemble((ASCII_SPARK if ascii else SPARK, INK), "  ", (NAME, f"bold {INK}"))


class Brand(Static):
    DEFAULT_CSS = """
    Brand { width: auto; height: 1; text-wrap: nowrap; }
    """

    def configure(self, ascii: bool = False) -> None:
        self.update(mark(ascii))
