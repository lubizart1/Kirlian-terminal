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
    # Added 2026-10-28; appended so earlier families keep their seeds.
    "aurora",
    "rain",
    "loops",
    "heartbeat",
    "comets",
    "lattice",
    "petals",
    "dunes",
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


@dataclass(frozen=True)
class Sound:
    """What the music is doing, each 0 to 1: bass, mids, treble, loudness, a recent hit.

    `pulse` grows on every hit and never shrinks, so rings can travel on kicks.
    Patterns drawn without a Sound are exactly the catalog's saved drawings.
    """

    bass: float = 0.0
    mid: float = 0.0
    treble: float = 0.0
    energy: float = 0.0
    hit: float = 0.0
    pulse: float = 0.0


@dataclass(frozen=True)
class Frame:
    """Ribbon text plus, per cell, 1.0 for a main stroke or 0.5 for a fine one behind it."""

    text: str
    depth: tuple[tuple[float, ...], ...]


class DotField:
    def __init__(self, width: int):
        self.width = max(1, min(MAX_WIDTH, width))
        self.extent = self.width * 2
        self.rows = [[0] * self.width for _ in range(HEIGHT)]
        self.front = [[0] * self.width for _ in range(HEIGHT)]

    def dot(self, x: float, y: float, back: bool = False) -> None:
        x, y = round(x), round(y)
        if 0 <= x < self.extent and 0 <= y < HEIGHT * 4:
            bit = BITS[y % 4][x % 2]
            self.rows[y // 4][x // 2] |= bit
            if not back:
                self.front[y // 4][x // 2] |= bit

    def line(
        self, x1: float, y1: float, x2: float, y2: float, stride: int = 1, back: bool = False
    ) -> None:
        steps = max(1, math.ceil(max(abs(x2 - x1), abs(y2 - y1))))
        for step in range(0, steps + 1, stride):
            t = step / steps
            self.dot(x1 + (x2 - x1) * t, y1 + (y2 - y1) * t, back)

    def text(self, characters: str) -> str:
        if not any(any(row) for row in self.rows):
            self.dot(self.extent // 2, 5)
        if characters == "ascii":
            return "\n".join("".join(ascii_cell(mask) for mask in row) for row in self.rows)
        return "\n".join("".join(chr(0x2800 + mask) for mask in row) for row in self.rows)

    def frame(self, characters: str) -> Frame:
        text = self.text(characters)
        depth = tuple(
            tuple(1.0 if front else 0.5 for front in front_row) for front_row in self.front
        )
        return Frame(text, depth)


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
    return render(family, variant, seconds, width, characters).text


def render(
    family: str,
    variant: int,
    seconds: float,
    width: int,
    characters: str,
    sound: Sound | None = None,
) -> Frame:
    """One frame. With `sound`, each family answers a different part of the music."""
    s = sound
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
                # Mids lift the thread; treble shakes loose more fine strands.
                lift = 0.7 + 0.6 * s.mid if s else 1.0
                y = center + envelope * amplitude * lift * (
                    0.75 * math.sin(x / spacing + t) + 0.25 * math.sin(x / 43 - t * 0.4)
                )
                field.dot(x, y)
                every = max(2, round(4 / (density * (1 + 1.5 * s.treble if s else 1))))
                if x % every == 0:
                    field.dot(x, y + math.sin(x / 11 - t * 0.6) * 1.3, back=True)
            elif family == "tides":
                # The swell rises and falls with the bass.
                swell = math.sin(x / (spacing * 1.8) - t)
                y = center + amplitude * envelope * swell * (0.45 + 1.0 * s.bass if s else 1.0)
                field.dot(x, y)
                if x % 3 != 0:
                    field.dot(x, y + 1.4 * math.sin(x / spacing + t * 0.5), back=True)
            else:
                drift = 0.6 * math.sin(x / 57 + t * 0.3)
                # Loud passages pull the two threads apart.
                apart = 0.55 + 0.8 * s.energy if s else 1.0
                wave = envelope * amplitude * apart * math.sin(x / (spacing * 0.7) + t)
                field.dot(x, center + drift + wave)
                field.dot(x, center + drift - wave, back=True)

    elif family == "ripples":
        origin = extent * rng.uniform(0.35, 0.65)
        maximum = max(spacing * 2.8, extent * 0.65)
        count = min(6, max(3, round(extent * density / (70 * profile.spacing))))
        step = maximum / count
        for ring in range(count):
            # Each kick pushes every ring outward, so a new one starts at the center.
            travel = t * 7 + (s.pulse * step if s else 0)
            radius = (ring * step + travel) % maximum
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
                outer = radius > maximum * 0.6
                field.dot(x, center - y, back=outer)
                field.dot(x, center + y, back=outer)

    elif family == "orbits":
        count = max(1, round(extent / (spacing * 3)))
        for orbit in range(count):
            origin = (orbit + 0.5) * extent / count
            radius = min(extent / count * 0.38, spacing) * (0.8 + 0.4 * s.bass if s else 1.0)
            # Hits nudge the satellites forward.
            turn = t + orbit * 1.7 + (s.pulse * 0.6 if s else 0)
            for point in range(max(20, round(radius * 4))):
                angle = point / max(20, round(radius * 4)) * math.tau
                if math.sin(angle - turn) > -0.55:
                    field.dot(
                        origin + radius * math.cos(angle),
                        center + amplitude * 0.7 * math.sin(angle),
                        back=True,
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
            if s:  # Branches reach further in loud passages and rest in quiet ones.
                reach *= 0.5 + 0.8 * s.energy
            for point in range(max(8, round(length * 2))):
                u = point / max(8, round(length * 2))
                x = origin + profile.direction * length * u
                y = stem(origin) + side * reach * math.sin(u * math.pi / 2)
                if family == "fronds":
                    field.dot(x + math.sin(u * math.pi) * 2, y)
                    if point % 5 == 0 and 0.2 < u < 0.85:
                        field.line(x, y, x - profile.direction * 3, y + side * 0.8, back=True)
                else:
                    field.dot(x, y + 0.35 * math.sin(u * 9 + t))
                    if point == round(length):
                        field.line(
                            x,
                            y,
                            x + profile.direction * length * 0.5,
                            y - side * reach * 0.55,
                            back=True,
                        )

    elif family in {"embers", "seeds"}:
        count = max(2, round(extent / (24 * profile.spacing) * density))
        if s and family == "embers":
            # More sparks in loud passages, and a burst on each hit.
            count = max(2, round(count * (0.6 + 1.2 * s.energy + 1.5 * s.hit)))
        for particle in range(count):
            origin = rng.uniform(0, extent)
            drift = rng.uniform(0.65, 1.1)
            x = (origin + t * 9 * drift) % (extent + 12) - 6
            y = center + amplitude * math.sin(origin / spacing + t * 0.6)
            if family == "embers":
                length = rng.randrange(4, 11)
                for tail in range(length):
                    if tail < 3 or tail % 2 == 0:
                        field.dot(
                            x - tail * profile.direction,
                            y + tail * 0.08 * math.sin(t),
                            back=tail >= 3,
                        )
            else:
                turn = 0.6 * math.sin(t * 0.5 + particle) * (1 + 1.2 * s.mid if s else 1)
                size = 0.8 + 0.5 * s.bass if s else 1.0  # Seeds swell with the bass.
                for point in range(14):
                    angle = point * math.tau / 14
                    dx, dy = 3 * size * math.cos(angle), 0.9 * size * math.sin(angle)
                    field.dot(
                        x + dx * math.cos(turn) - dy * math.sin(turn),
                        y + dx * math.sin(turn) + dy * math.cos(turn),
                    )
                field.line(x - 2, y, x - 6, y - 0.7 * math.cos(t + particle), back=True)

    elif family == "aurora":
        # Curtains of light hang from a rippling hem; treble lengthens them.
        stride = max(1, round(2 / density))
        for x in range(0, extent, stride):
            u = x / max(1, extent - 1)
            envelope = math.sin(math.pi * u) ** 0.4
            hem = 1.4 + 1.0 * math.sin(x / (spacing * 1.3) + t) + 0.5 * math.sin(x / 9 - t * 1.7)
            glow = 0.25 + 0.75 * (0.5 + 0.5 * math.sin(x / (spacing * 0.45) - t * 0.8))
            reach = 11 * profile.amplitude * envelope * glow
            if s:
                reach *= 0.55 + 0.9 * s.treble
            field.dot(x, hem)
            for k in range(1, int(reach) + 1):
                if k < 3 or (k + x // stride) % 2 == 0:
                    field.dot(x + k * 0.2 * profile.direction, hem + k, back=True)

    elif family == "rain":
        # Slanting streaks; louder music brings heavier rain, splashes at the bottom.
        count = max(3, round(extent / (10 * profile.spacing) * density))
        if s:
            count = max(3, round(count * (0.5 + 1.3 * s.energy)))
        slant = 0.6 * profile.direction
        for _drop in range(count):
            origin = rng.uniform(0, extent)
            speed = rng.uniform(0.8, 1.3)
            fall = (rng.uniform(0, 16) + seconds * profile.speed * 30 * speed) % 16 - 2
            x = origin + fall * slant
            for k in range(3):
                field.dot(x - k * slant, fall - k, back=k > 0)
            if fall > 10.5:
                field.dot(x - 1.5, 11, back=True)
                field.dot(x + 1.5, 11, back=True)

    elif family == "loops":
        # Lissajous figures, each with a faint echo a moment behind.
        count = max(1, round(extent / (spacing * 2.6)))
        ratio_x, ratio_y = 1 + variant % 3, 2 + variant % 2
        for loop in range(count):
            cx = (loop + 0.5) * extent / count
            rx = min(extent / count * 0.42, spacing * 1.1) * (0.75 + 0.5 * s.energy if s else 1)
            ry = amplitude * 0.85
            points = max(40, round(rx * 6))
            for echo, lag in ((False, 0.0), (True, 0.5)):
                turn = t + loop * 0.9 - lag
                for k in range(points):
                    angle = k / points * math.tau
                    if echo and k % 3:
                        continue
                    field.dot(
                        cx + rx * math.sin(ratio_x * angle + turn),
                        center + ry * math.sin(ratio_y * angle),
                        back=echo,
                    )

    elif family == "heartbeat":
        # A trace with beats travelling along it; hits make the spikes jump.
        height = amplitude * 1.35 * (0.55 + 0.6 * s.hit + 0.35 * s.energy if s else 1.0)
        period = spacing * 5

        def beat(dx: float) -> float:
            if -6 <= dx < -3:
                return -0.15 * math.sin((dx + 6) / 3 * math.pi)
            if 0 <= dx < 1.5:
                return -dx / 1.5
            if 1.5 <= dx < 3:
                return -1 + (dx - 1.5) / 1.5 * 1.5
            if 3 <= dx < 5:
                return 0.5 - (dx - 3) / 2 * 0.5
            if 7 <= dx < 11:
                return -0.25 * math.sin((dx - 7) / 4 * math.pi)
            return 0.0

        travel = (seconds * profile.speed * 40) * profile.direction
        for x in range(extent):
            offset = 0.0
            for k in range(int(extent / period) + 2):
                start = (k * period + travel) % (extent + period) - period / 2
                offset += beat((x - start) / (1.8 * profile.spacing))
            field.dot(x, center + height * offset, back=offset == 0 and x % 2 == 1)

    elif family == "comets":
        # Bright heads trailing long, fading tails; hits flare the heads.
        count = max(2, round(extent / (spacing * 2.5) * density))
        for comet in range(count):
            speed = rng.uniform(0.7, 1.2)
            x = (rng.uniform(0, extent) + seconds * profile.speed * 70 * speed) % (extent + 40)
            x = (x - 20) if profile.direction > 0 else extent - (x - 20)

            def path(position: float, comet: int = comet) -> float:
                return center + amplitude * 0.8 * math.sin(position / spacing + comet * 1.3)

            y = path(x)
            field.dot(x, y)
            field.dot(x + profile.direction, y)
            if not s or s.hit > 0.3 or comet % 2 == 0:
                field.dot(x, y - 1)
                field.dot(x, y + 1)
            for k in range(2, round(34 * density)):
                tail = x - k * profile.direction
                if k < 5 or k % 2 == 0:
                    field.dot(tail, path(tail), back=True)

    elif family == "lattice":
        # A drifting diamond net; the bass widens its mesh.
        gap = spacing * 0.9 * (0.8 + 0.45 * s.bass if s else 1.0)
        for x in range(extent):
            u = x / max(1, extent - 1)
            half = 1 + math.sin(math.pi * u) ** 0.6 * amplitude
            for y in range(HEIGHT * 4):
                if abs(y - center) > half:
                    continue
                if (x + y * 1.6 + t * 6) % gap < 1:
                    field.dot(x, y)
                if (x - y * 1.6 - t * 4) % gap < 1:
                    field.dot(x, y, back=True)

    elif family == "petals":
        # Small turning flowers; loud passages open them wider.
        count = max(1, round(extent / (spacing * 2.4) * density))
        lobes = 2 + variant % 4
        for flower in range(count):
            cx = (flower + 0.5) * extent / count + 3 * math.sin(t * 0.3 + flower)
            radius = min(extent / count * 0.4, spacing) * (0.7 + 0.5 * s.energy if s else 1.0)
            turn = t * 0.5 + flower
            points = max(48, round(radius * 8))
            for k in range(points):
                angle = k / points * math.tau
                r = math.cos(lobes * angle)
                x = cx + radius * r * math.cos(angle + turn)
                y = center + amplitude * 0.9 * r * math.sin(angle + turn)
                field.dot(x, y, back=abs(r) < 0.45)
            field.dot(cx, center)

    elif family == "dunes":
        # Three ranges of hills sliding at different speeds; the bass lifts the nearest.
        layers = ((1.0, 1.0, 1.4, False), (0.5, 0.7, -0.6, True), (0.25, 0.45, -2.6, True))
        for index, (pace, height, offset, back) in enumerate(layers):
            lift = 0.5 + 0.9 * s.bass if s and index == 0 else 1.0
            for x in range(extent):
                if back and x % 2:
                    continue
                wave = math.sin(x / (spacing * 0.55) + t * pace * 2 + index * 2.1)
                ripple = 0.4 * math.sin(x / (spacing * 0.25) - t * pace * 1.2)
                y = center + offset + amplitude * 0.75 * height * lift * (wave + ripple)
                field.dot(x, y, back=back)

    else:  # constellations
        count = max(2, round(extent / (25 * profile.spacing) * density))
        previous = None
        for star in range(count):
            x = (star + rng.uniform(0.1, 0.9)) * extent / count
            y = center + amplitude * math.sin(star * 2.3 + phase) + 0.5 * math.sin(t + star)
            field.dot(x, y)
            # Cymbals and treble make more stars flare at once.
            threshold = 0.15 - 1.1 * s.treble if s else 0.15
            if math.sin(t * 0.7 + star * 2.1) > threshold:
                field.dot(x - 1, y)
                field.dot(x + 1, y)
                field.dot(x, y - 1)
                field.dot(x, y + 1)
            if previous and star % 3:
                field.line(*previous, x, y, stride=4, back=True)
            previous = x, y

    return field.frame(characters)
