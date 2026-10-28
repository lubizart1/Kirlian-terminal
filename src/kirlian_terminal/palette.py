# SPDX-License-Identifier: GPL-3.0-or-later
"""Small, deterministic color studies from local album artwork."""

from __future__ import annotations

import colorsys
import math

from PIL import Image


def rgb(color: str) -> tuple[int, int, int]:
    return tuple(int(color[index : index + 2], 16) for index in (1, 3, 5))


def hex_color(color) -> str:
    return "#" + "".join(f"{round(channel):02x}" for channel in color)


def mix(first: str, second: str, amount: float) -> str:
    return hex_color(a + (b - a) * amount for a, b in zip(rgb(first), rgb(second), strict=True))


def readable(color: tuple[int, int, int]) -> str:
    """Preserve the cover's hue, lifting dark colors and softening saturation."""
    hue, lightness, saturation = colorsys.rgb_to_hls(*(channel / 255 for channel in color))
    lightness = max(0.68, min(0.82, lightness))
    saturation = min(0.62, saturation)
    return hex_color(channel * 255 for channel in colorsys.hls_to_rgb(hue, lightness, saturation))


def extract_palette(image: Image.Image | None) -> tuple[str, ...]:
    """Choose up to three substantial, distinct cover colors; never alter the image."""
    if image is None:
        return ()
    sample = image.convert("RGB")
    sample.thumbnail((64, 64), Image.Resampling.LANCZOS)
    quantized = sample.quantize(colors=8, method=Image.Quantize.MEDIANCUT).convert("RGB")
    swatches = quantized.getcolors(64 * 64) or []
    total = sample.width * sample.height
    substantial = [(count, color) for count, color in swatches if count >= total * 0.03]
    colorful = [
        (count, color)
        for count, color in substantial
        if colorsys.rgb_to_hls(*(channel / 255 for channel in color))[2] >= 0.18
        and 0.08 < sum(color) / (3 * 255) < 0.94
    ]
    candidates = sorted(colorful or substantial or swatches, key=lambda item: (-item[0], item[1]))
    selected: list[tuple[int, int, int]] = []
    for _, color in candidates:
        if all(math.dist(color, previous) > 55 for previous in selected):
            selected.append(color)
        if len(selected) == 3:
            break
    return tuple(dict.fromkeys(readable(color) for color in selected))


def ribbon_color(colors: tuple[str, ...], fraction: float) -> str:
    """Interpolate gently across the selected colors without cycling over time."""
    position = max(0, min(1, fraction)) * (len(colors) - 1)
    index = min(int(position), len(colors) - 1)
    return mix(colors[index], colors[min(index + 1, len(colors) - 1)], position - index)
