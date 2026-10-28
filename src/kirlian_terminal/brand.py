# SPDX-License-Identifier: GPL-3.0-or-later
"""A hand-drawn terminal wordmark, independent of image protocols.

The drawn mark uses the same Braille dot grid as the filament ribbon. Paths below
describe just the six letters we need; no font, image, or general text rasterizer.
"""

import math
from functools import cache

from rich.text import Text
from textual.widgets import Static

from .appearance import INK

# Letter width and connected strokes on an eight-dot-high drawing grid.
LETTERS = {
    "k": (5, (((0, 0), (0, 7)), ((4, 3), (0, 5), (4, 7)))),
    "i": (1, (((0, 0), (0, 0)), ((0, 3), (0, 7)))),
    "r": (4, (((0, 3), (0, 7)), ((0, 4), (1, 3), (3, 3)))),
    "l": (2, (((0, 0), (0, 6), (1, 7)),)),
    "a": (5, (((1, 3), (3, 3), (4, 4), (4, 7)), ((4, 5), (1, 5), (0, 6), (1, 7), (3, 7), (4, 6)))),
    "n": (5, (((0, 3), (0, 7)), ((0, 4), (1, 3), (3, 3), (4, 4), (4, 7)))),
}

# The basic character set keeps ordinary lettering legible at the smaller size.
ASCII_MARK = ("\\|/  kirlian", "/|\\         ")


@cache
def drawn_wordmark() -> str:
    dots: set[tuple[int, int]] = set()

    def stroke(points, offset=0):
        for start, end in zip(points, points[1:], strict=False):
            distance = max(abs(end[0] - start[0]), abs(end[1] - start[1]), 1)
            for step in range(distance + 1):
                t = step / distance
                dots.add(
                    (
                        round(start[0] + (end[0] - start[0]) * t) + offset,
                        round(start[1] + (end[1] - start[1]) * t),
                    )
                )

    # Open-centered rays, rather than a solid asterisk.
    for ray in range(8):
        angle = ray * math.tau / 8
        stroke(
            tuple(
                (round(3.5 + math.cos(angle) * radius), round(3.5 + math.sin(angle) * radius))
                for radius in (2.25, 3.5)
            )
        )

    x = 12
    for letter in "kirlian":
        width, paths = LETTERS[letter]
        for path in paths:
            stroke(path, x)
        x += width + 2

    bits = ((1, 8), (2, 16), (4, 32), (64, 128))
    return "\n".join(
        "".join(
            chr(
                0x2800
                + sum(
                    bits[dy][dx]
                    for dy in range(4)
                    for dx in range(2)
                    if (column * 2 + dx, row * 4 + dy) in dots
                )
            )
            for column in range((x - 1) // 2)
        ).replace(chr(0x2800), " ")
        for row in range(2)
    )


class Brand(Static):
    DEFAULT_CSS = """
    Brand { width: 24; height: 2; text-wrap: nowrap; overflow: hidden; }
    """

    def __init__(self, mode: str, **kwargs):
        super().__init__(**kwargs)
        self.mode = mode
        self.compact = False

    def on_mount(self) -> None:
        self.configure(self.mode, self.compact)

    def configure(self, mode: str, compact: bool = False, ascii: bool = False) -> None:
        self.mode, self.compact = mode, compact
        if compact or mode == "text":
            content = "*  kirlian" if ascii else "✳  kirlian"
        else:
            content = "\n".join(ASCII_MARK) if ascii else drawn_wordmark()
        self.update(Text(content, style=INK))
