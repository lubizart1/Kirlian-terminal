# SPDX-License-Identifier: GPL-3.0-or-later
"""Small, deterministic ASCII studies. Animation time is independent of audio time."""

from __future__ import annotations

import math
import random
import secrets
from dataclasses import dataclass, field

from .patterns import FAMILIES, PROFILES
from .patterns import ribbon_frame as catalog_frame

LEGACY_FAMILIES = ("filaments", "ripples")
WIDTH = 24
HEIGHT = 3


@dataclass(frozen=True)
class Variation:
    family: str
    seed: int
    version: int = 1

    @property
    def code(self) -> str:
        return f"v{self.version}:{self.family}:{self.seed:08x}"

    @property
    def label(self) -> str:
        detail = PROFILES[self.seed].name if self.version == 2 else f"{self.seed:08x}"
        return f"{self.family.title()} · {detail}"

    @classmethod
    def parse(cls, code: str) -> Variation:
        version, family, seed = code.split(":")
        value = int(seed, 16)
        if version == "v1" and family in LEGACY_FAMILIES and 0 <= value < 2**32:
            return cls(family, value)
        if version == "v2" and family in FAMILIES and 0 <= value < len(PROFILES):
            return cls(family, value, version=2)
        raise ValueError("Unknown animation")

    @classmethod
    def choose(cls, previous: Variation | None = None) -> Variation:
        return secrets.choice([v for v in CATALOG if not previous or v.family != previous.family])

    def frame(self, seconds: float) -> str:
        if self.version == 2:
            return self.ribbon_frame(seconds, WIDTH, "ascii")
        rng = random.Random(self.seed)
        speed = rng.uniform(0.25, 0.55)
        direction = rng.choice((-1, 1))
        phase = rng.uniform(0, math.tau)
        spacing = rng.uniform(3.5, 6.5)
        time = seconds * speed * direction + phase
        cells = [[" "] * WIDTH for _ in range(HEIGHT)]
        if self.family == "filaments":
            # A continuous wandering thread, with quiet sparks beside it.
            for x in range(WIDTH):
                wave = math.sin(x / spacing + time)
                y = min(HEIGHT - 1, max(0, round(1 + wave)))
                previous = round(1 + math.sin((x - 1) / spacing + time))
                cells[y][x] = "~" if y == previous else "/" if y < previous else "\\"
                if (x + self.seed) % 9 == 0:
                    cells[(y + 1) % HEIGHT][x] = "."
        else:
            # Elliptical rings drift out from a stable, seed-selected origin.
            origin = rng.uniform(6, WIDTH - 6)
            for y in range(HEIGHT):
                for x in range(WIDTH):
                    distance = math.hypot((x - origin) / 2.5, (y - 1) * 1.15)
                    ring = (distance - time) % spacing
                    if ring < 0.52:
                        cells[y][x] = "(" if x < origin else ")"
                    elif ring < 0.82 and y == 1:
                        cells[y][x] = "."
        return "\n".join("".join(row) for row in cells)

    def ribbon_frame(self, seconds: float, width: int, characters: str = "dots") -> str:
        """The catalog uses v2 recipes; keep saved v1 ribbons pixel-for-pixel."""
        if self.version == 2:
            return catalog_frame(self.family, self.seed, seconds, width, characters)
        width = max(1, min(400, width))
        rng = random.Random(self.seed)
        phase = rng.uniform(0, math.tau)
        speed = rng.uniform(0.24, 0.42) * rng.choice((-1, 1))
        spacing = rng.uniform(16, 26)
        time = seconds * speed + phase
        pixels = [[False] * (width * 2) for _ in range(HEIGHT * 4)]

        def dot(x: float, y: float) -> None:
            xi, yi = round(x), round(y)
            if 0 <= xi < width * 2 and 0 <= yi < HEIGHT * 4:
                pixels[yi][xi] = True

        for x in range(width * 2):
            envelope = math.sin(math.pi * x / max(1, width * 2 - 1)) ** 0.7
            wave = math.sin(x / spacing + time)
            y = 5.5 + envelope * (wave * 3 + math.sin(x / 43 - time * 0.4) * 1.4)
            dot(x, y)
            if x % 3 == 0:
                dot(x, y + math.sin(x / 11 - time * 0.6) * 1.3)
            if self.family == "ripples":
                dot(x, 11 - y)
        for k in range(max(1, width // 28)):
            dot((k * 53 + self.seed) % (width * 2), 5 + math.sin(k + time * 0.2) * 3)

        if characters == "ascii":
            cells = [[" "] * width for _ in range(HEIGHT)]
            for x in range(width):
                ys = [y for y in range(HEIGHT * 4) if pixels[y][x * 2]]
                if ys:
                    y = round(sum(ys) / len(ys))
                    cells[min(HEIGHT - 1, y // 4)][x] = "~" if x % 3 == 0 else "-"
            return "\n".join("".join(row) for row in cells)
        bits = ((1, 8), (2, 16), (4, 32), (64, 128))
        return "\n".join(
            "".join(
                chr(
                    0x2800
                    + sum(
                        bits[dy][dx]
                        for dy in range(4)
                        for dx in range(2)
                        if pixels[row * 4 + dy][col * 2 + dx]
                    )
                )
                for col in range(width)
            )
            for row in range(HEIGHT)
        )


CATALOG = tuple(
    Variation(family, variant, version=2) for family in FAMILIES for variant in range(len(PROFILES))
)


@dataclass
class PatternDeck:
    """Use every catalog entry before refilling; prefer a different family next."""

    remaining: list[Variation] = field(default_factory=list)

    def next(self, previous: Variation | None = None) -> Variation:
        if not self.remaining:
            self.remaining = list(CATALOG)
        available = [v for v in self.remaining if v != previous]
        if not available:  # The last entry may have just been recalled manually.
            self.remaining = list(CATALOG)
            available = [v for v in self.remaining if v != previous]
        candidates = [v for v in available if not previous or v.family != previous.family]
        result = secrets.choice(candidates or available)
        self.remaining.remove(result)
        return result


@dataclass
class AnimationClock:
    variation: Variation = field(default_factory=Variation.choose)
    elapsed: float = 0
    anchor: float | None = None
    serial: int = 0
    deck: PatternDeck = field(default_factory=PatternDeck, repr=False)

    def __post_init__(self) -> None:
        # Count the initial catalog selection as the first draw of this session.
        if not self.deck.remaining:
            self.deck.remaining = [v for v in CATALOG if v != self.variation]

    def time(self, now: float) -> float:
        return self.elapsed + (max(0, now - self.anchor) if self.anchor is not None else 0)

    def running(self, active: bool, now: float) -> None:
        self.elapsed = self.time(now)
        self.anchor = now if active else None

    def select(self, variation: Variation, now: float) -> None:
        self.variation = variation
        self.elapsed = 0
        if self.anchor is not None:
            self.anchor = now

    def shuffle(self, now: float) -> None:
        self.select(self.deck.next(self.variation), now)

    def observe(self, serial: int, active: bool, now: float) -> None:
        if serial and serial != self.serial:
            self.shuffle(now)
            self.serial = serial
        self.running(active, now)
