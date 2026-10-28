# SPDX-License-Identifier: GPL-3.0-or-later
"""Ten quiet ribbon motifs, each with ten stable, locally generated variations.

Render directly into Braille cell masks: no images, simulation history, or IO.
Changing a v2 recipe changes a saved pattern, so future redesigns need a new version.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

FAMILIES = (
    "filaments",
    "tides",
    "braids",
    "ripples",
    "orbits",
    "fronds",
    "mycelium",
    "embers",
    "seeds",
    "constellations",
)
HEIGHT = 3
MAX_WIDTH = 400
BITS = ((1, 8), (2, 16), (4, 32), (64, 128))


@dataclass(frozen=True)
class Profile:
    name: str
    speed: float
    direction: int
    spacing: float
    amplitude: float
    density: float


PROFILES = (
    Profile("Drift", 0.20, 1, 1.00, 0.75, 0.80),
    Profile("Undercurrent", 0.19, -1, 1.15, 0.85, 1.00),
    Profile("Glimmer", 0.28, 1, 0.80, 0.55, 0.65),
    Profile("Breath", 0.12, -1, 1.35, 1.00, 0.60),
    Profile("Current", 0.32, 1, 0.70, 0.95, 0.90),
    Profile("Stillwater", 0.14, 1, 1.45, 0.45, 0.60),
    Profile("Weave", 0.25, -1, 0.90, 0.80, 1.20),
    Profile("Dusk", 0.16, -1, 1.20, 0.70, 0.55),
    Profile("Bloom", 0.20, 1, 1.00, 1.00, 1.10),
    Profile("Whisper", 0.10, -1, 1.60, 0.40, 0.45),
)


class DotField:
    def __init__(self, width: int):
        self.width = max(1, min(MAX_WIDTH, width))
        self.extent = self.width * 2
        self.rows = [[0] * self.width for _ in range(HEIGHT)]

    def dot(self, x: float, y: float) -> None:
        x, y = round(x), round(y)
        if 0 <= x < self.extent and 0 <= y < HEIGHT * 4:
            self.rows[y // 4][x // 2] |= BITS[y % 4][x % 2]

    def line(self, x1: float, y1: float, x2: float, y2: float, stride: int = 1) -> None:
        steps = max(1, math.ceil(max(abs(x2 - x1), abs(y2 - y1))))
        for step in range(0, steps + 1, stride):
            t = step / steps
            self.dot(x1 + (x2 - x1) * t, y1 + (y2 - y1) * t)

    def text(self, characters: str) -> str:
        if not any(any(row) for row in self.rows):
            self.dot(self.extent // 2, 5)
        if characters == "ascii":
            return "\n".join("".join(ascii_cell(mask) for mask in row) for row in self.rows)
        return "\n".join("".join(chr(0x2800 + mask) for mask in row) for row in self.rows)


def ascii_cell(mask: int) -> str:
    """Preserve multiple strands in each row instead of averaging them together."""
    if not mask:
        return " "
    ys = [dy for dy in range(4) for dx in range(2) if mask & BITS[dy][dx]]
    if max(ys) - min(ys) <= 1:
        return "-" if mask.bit_count() > 1 else "'" if min(ys) < 2 else "."
    left = [dy for dy in range(4) if mask & BITS[dy][0]]
    right = [dy for dy in range(4) if mask & BITS[dy][1]]
    if not left or not right:
        return "|"
    slope = sum(right) / len(right) - sum(left) / len(left)
    return "/" if slope < -0.5 else "\\" if slope > 0.5 else ":"


def ribbon_frame(family: str, variant: int, seconds: float, width: int, characters: str) -> str:
    profile = PROFILES[variant]
    rng = random.Random(0x4B49524C + FAMILIES.index(family) * 997 + variant * 131)
    phase = rng.uniform(0, math.tau)
    t = seconds * profile.speed * profile.direction + phase
    field = DotField(width)
    extent = field.extent
    spacing = 22 * profile.spacing
    amplitude = 4.4 * profile.amplitude
    center = 5.5
    density = profile.density

    if family in {"filaments", "tides", "braids"}:
        for x in range(extent):
            u = x / max(1, extent - 1)
            envelope = math.sin(math.pi * u) ** 0.6
            if family == "filaments":
                y = center + envelope * amplitude * (
                    0.75 * math.sin(x / spacing + t) + 0.25 * math.sin(x / 43 - t * 0.4)
                )
                field.dot(x, y)
                if x % max(2, round(4 / density)) == 0:
                    field.dot(x, y + math.sin(x / 11 - t * 0.6) * 1.3)
            elif family == "tides":
                swell = math.sin(x / (spacing * 1.8) - t)
                y = center + amplitude * envelope * swell
                field.dot(x, y)
                if x % 3 != 0:
                    field.dot(x, y + 1.4 * math.sin(x / spacing + t * 0.5))
            else:
                drift = 0.6 * math.sin(x / 57 + t * 0.3)
                wave = envelope * amplitude * math.sin(x / (spacing * 0.7) + t)
                field.dot(x, center + drift + wave)
                field.dot(x, center + drift - wave)

    elif family == "ripples":
        origin = extent * rng.uniform(0.35, 0.65)
        maximum = max(spacing * 2.8, extent * 0.65)
        count = min(6, max(3, round(extent * density / (70 * profile.spacing))))
        step = maximum / count
        for ring in range(count):
            radius = (ring * step + t * 7) % maximum
            height = amplitude * (0.35 + 0.65 * radius / maximum)
            if radius < 1:
                field.dot(origin, center)
                continue
            # Sample visible columns only; wide windows must not multiply the
            # ring count or trace thousands of off-screen trigonometric points.
            for x in range(
                max(0, math.ceil(origin - radius)), min(extent, math.floor(origin + radius) + 1)
            ):
                y = height * math.sqrt(max(0, 1 - ((x - origin) / radius) ** 2))
                field.dot(x, center - y)
                field.dot(x, center + y)

    elif family == "orbits":
        count = max(1, round(extent / (spacing * 3)))
        for orbit in range(count):
            origin = (orbit + 0.5) * extent / count
            radius = min(extent / count * 0.38, spacing)
            turn = t + orbit * 1.7
            for point in range(max(20, round(radius * 4))):
                angle = point / max(20, round(radius * 4)) * math.tau
                if math.sin(angle - turn) > -0.55:
                    field.dot(
                        origin + radius * math.cos(angle),
                        center + amplitude * 0.7 * math.sin(angle),
                    )
            x, y = origin + radius * math.cos(turn), center + amplitude * 0.7 * math.sin(turn)
            field.dot(x, y)
            field.dot(x + 1, y)
            field.dot(x, y - 1)

    elif family in {"fronds", "mycelium"}:

        def stem(x):
            return center + 0.7 * math.sin(x / spacing + t * 0.4)

        for x in range(extent):
            field.dot(x, stem(x))
        step = max(10, round(spacing / density))
        for branch, origin in enumerate(range(step // 2, extent, step)):
            side = -1 if branch % 2 else 1
            length = step * rng.uniform(0.45, 0.8)
            reach = amplitude * (0.75 + 0.2 * math.sin(t + branch))
            for point in range(max(8, round(length * 2))):
                u = point / max(8, round(length * 2))
                x = origin + profile.direction * length * u
                y = stem(origin) + side * reach * math.sin(u * math.pi / 2)
                if family == "fronds":
                    field.dot(x + math.sin(u * math.pi) * 2, y)
                    if point % 5 == 0 and 0.2 < u < 0.85:
                        field.line(x, y, x - profile.direction * 3, y + side * 0.8)
                else:
                    field.dot(x, y + 0.35 * math.sin(u * 9 + t))
                    if point == round(length):
                        field.line(
                            x, y, x + profile.direction * length * 0.5, y - side * reach * 0.55
                        )

    elif family in {"embers", "seeds"}:
        count = max(2, round(extent / (24 * profile.spacing) * density))
        for particle in range(count):
            origin = rng.uniform(0, extent)
            drift = rng.uniform(0.65, 1.1)
            x = (origin + t * 9 * drift) % (extent + 12) - 6
            y = center + amplitude * math.sin(origin / spacing + t * 0.6)
            if family == "embers":
                length = rng.randrange(4, 11)
                for tail in range(length):
                    if tail < 3 or tail % 2 == 0:
                        field.dot(x - tail * profile.direction, y + tail * 0.08 * math.sin(t))
            else:
                turn = 0.6 * math.sin(t * 0.5 + particle)
                for point in range(14):
                    angle = point * math.tau / 14
                    dx, dy = 3 * math.cos(angle), 0.9 * math.sin(angle)
                    field.dot(
                        x + dx * math.cos(turn) - dy * math.sin(turn),
                        y + dx * math.sin(turn) + dy * math.cos(turn),
                    )
                field.line(x - 2, y, x - 6, y - 0.7 * math.cos(t + particle))

    else:  # constellations
        count = max(2, round(extent / (25 * profile.spacing) * density))
        previous = None
        for star in range(count):
            x = (star + rng.uniform(0.1, 0.9)) * extent / count
            y = center + amplitude * math.sin(star * 2.3 + phase) + 0.5 * math.sin(t + star)
            field.dot(x, y)
            if math.sin(t * 0.7 + star * 2.1) > 0.15:
                field.dot(x - 1, y)
                field.dot(x + 1, y)
                field.dot(x, y - 1)
                field.dot(x, y + 1)
            if previous and star % 3:
                field.line(*previous, x, y, stride=4)
            previous = x, y

    return field.text(characters)
