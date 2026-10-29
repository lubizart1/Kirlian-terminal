# SPDX-License-Identifier: GPL-3.0-or-later
"""Live audio levels and the amp's equalizer, both run inside the owned mpv.

Levels come from FFmpeg filters inside mpv's own filter list. A copy of the
playing audio is folded to mono and split through twenty band-pass filters; the
bands ride along as extra channels next to the real stereo signal, `astats`
measures every channel, and `pan` drops the extra channels again, so what you hear
is the stereo signal untouched. mpv exposes the measurements of the latest frame
as the `af-metadata/meter` property. The equalizer is a chain of FFmpeg
`equalizer` filters with a preamp and balance stage. When it is off, the chain is
removed, so the audio is exactly what it was without the amp.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field, replace

from .i18n import N_
from .library import Library
from .patterns import Sound

BANDS = (31, 62, 125, 250, 500, 1000, 2000, 4000, 8000, 16000)
GAIN_LIMIT = 12.0
PREAMP_RANGE = (-12.0, 6.0)
SILENCE = -60.0
REPLAYGAIN = ("no", "track", "album")
# Twenty log-spaced analysis bands from 40 Hz to 16 kHz, half an octave wide.
SPECTRUM = tuple(round(40 * (16000 / 40) ** (index / 19)) for index in range(20))
SPECTRUM_FLOOR = -90.0


def meter_graph() -> str:
    """Measure the stereo signal and twenty bands, then output only the stereo signal."""
    count = len(SPECTRUM)
    splits = "".join(f"[s{index}]" for index in range(count))
    bands = "".join(f"[b{index}]" for index in range(count))
    parts = [
        # Stereo in, stereo out: mono files play on both sides, surround is folded.
        "aformat=channel_layouts=stereo,asplit=2[main][copy]",
        f"[copy]pan=mono|c0=0.5*c0+0.5*c1,asplit={count}{splits}",
        *(
            f"[s{index}]bandpass=f={frequency}:t=o:w=0.5[b{index}]"
            for index, frequency in enumerate(SPECTRUM)
        ),
        f"[main]{bands}amerge=inputs={count + 1},"
        "astats=metadata=1:reset=1:measure_overall=none:measure_perchannel=RMS_level+Peak_level,"
        "pan=stereo|c0=c0|c1=c1,aspectralstats=measure=centroid+flux",
    ]
    return f"@meter:lavfi=[{';'.join(parts)}]"


METER = meter_graph()
# Shapes in dB per band, 31 Hz to 16 kHz. Gentle by design: boosts clip easily.
PRESETS: dict[str, tuple[float, ...]] = {
    N_("Flat"): (0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
    N_("Bass"): (6, 5, 4, 2, 0, 0, 0, 0, 0, 0),
    N_("Rock"): (4, 3, 1, -1, -2, -1, 1, 3, 4, 4),
    N_("Pop"): (-1, 1, 3, 4, 3, 0, -1, -1, 1, 2),
    N_("Jazz"): (3, 2, 1, 2, -1, -1, 0, 1, 2, 3),
    N_("Classical"): (0, 0, 0, 0, 0, 0, -2, -3, -3, -4),
    N_("Dance"): (5, 4, 2, 0, 0, -2, -2, -2, 0, 1),
    N_("Vocal"): (-2, -2, -1, 1, 3, 4, 3, 1, 0, -1),
    N_("Treble"): (0, 0, 0, 0, 0, 1, 2, 4, 5, 6),
}


def clamp(value: float, low: float, high: float) -> float:
    return min(high, max(low, value))


@dataclass(frozen=True)
class Tempo:
    """Speed and pitch for this session. Not saved: songs start normal next launch."""

    speed: float = 1.0  # 0.5 to 2.0
    semitones: int = 0  # -12 to +12
    tape: bool = False  # Pitch follows speed, like a record played faster or slower.

    @property
    def normal(self) -> bool:
        return self.speed == 1.0 and self.semitones == 0 and not self.tape

    @property
    def pitch(self) -> float:
        return 2 ** (self.semitones / 12)

    def with_speed(self, step: int | None) -> Tempo:
        speed = 1.0 if step is None else clamp(round(self.speed + step * 0.05, 2), 0.5, 2.0)
        return replace(self, speed=speed)

    def with_semitones(self, step: int | None) -> Tempo:
        value = 0 if step is None else int(clamp(self.semitones + step, -12, 12))
        return replace(self, semitones=value)


@dataclass(frozen=True)
class AmpSettings:
    visible: bool = False
    enabled: bool = False
    gains: tuple[float, ...] = PRESETS["Flat"]
    preamp: float = 0.0
    balance: float = 0.0
    preset: str = "Flat"
    replaygain: str = "no"

    @classmethod
    def load(cls, library: Library) -> AmpSettings:
        try:
            stored = json.loads(library.setting("amp") or "{}")
        except ValueError:
            stored = {}
        if not isinstance(stored, dict):
            return cls()
        default = cls()
        try:
            gains = tuple(clamp(float(g), -GAIN_LIMIT, GAIN_LIMIT) for g in stored.get("gains", ()))
            return cls(
                visible=bool(stored.get("visible", False)),
                enabled=bool(stored.get("enabled", False)),
                gains=gains if len(gains) == len(BANDS) else default.gains,
                preamp=clamp(float(stored.get("preamp", 0)), *PREAMP_RANGE),
                balance=clamp(float(stored.get("balance", 0)), -1, 1),
                preset=stored.get("preset", "Flat")
                if stored.get("preset", "Flat") in PRESETS
                else "",
                replaygain=stored.get("replaygain")
                if stored.get("replaygain") in REPLAYGAIN
                else "no",
            )
        except (TypeError, ValueError):
            return default

    def save(self, library: Library) -> None:
        library.set_setting("amp", json.dumps(asdict(self)))

    def with_gain(self, band: int, gain: float) -> AmpSettings:
        gains = list(self.gains)
        gains[band] = clamp(round(gain), -GAIN_LIMIT, GAIN_LIMIT)
        return replace(self, gains=tuple(gains), preset="", enabled=True)

    def with_preset(self, name: str) -> AmpSettings:
        return replace(self, gains=PRESETS[name], preset=name, enabled=True)

    def filters(self) -> str:
        """The mpv `af` list: equalizer (when on) before the meter, so levels show what plays."""
        if not self.enabled:
            return METER
        stages = [
            f"equalizer@b{index}=f={frequency}:t=o:w=1:g={gain:g}"
            for index, (frequency, gain) in enumerate(zip(BANDS, self.gains, strict=True))
        ]
        stages.append(f"volume@pre=volume={self.preamp:g}dB")
        stages.append(f"stereotools@bal=balance_out={self.balance:g}")
        return f"@eq:lavfi=[{','.join(stages)}],{METER}"


def decibels(value: object, floor: float = SILENCE) -> float:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return floor
    return floor if math.isnan(number) else clamp(number, floor, 6.0)


@dataclass(frozen=True)
class Levels:
    """One frame of what is playing: per-channel dB, band dB, brightness, and change."""

    rms: tuple[float, ...] = (SILENCE, SILENCE)
    peak: tuple[float, ...] = (SILENCE, SILENCE)
    centroid: float = 0.0
    flux: float = 0.0
    bands: tuple[float, ...] = ()  # RMS dB per SPECTRUM band, low to high

    @classmethod
    def parse(cls, metadata: object) -> Levels:
        if not isinstance(metadata, dict):
            return cls()

        def channels(name: str) -> tuple[float, ...]:
            values = [
                decibels(metadata.get(f"lavfi.astats.{n}.{name}"))
                for n in (1, 2)
                if f"lavfi.astats.{n}.{name}" in metadata
            ]
            if len(values) == 1:  # Mono plays from both sides.
                values *= 2
            return tuple(values) or (SILENCE, SILENCE)

        def spectral(name: str) -> float:
            values = []
            for n in (1, 2):
                try:
                    value = float(metadata.get(f"lavfi.aspectralstats.{n}.{name}", "nan"))
                except (TypeError, ValueError):
                    continue
                if not math.isnan(value):
                    values.append(value)
            return sum(values) / len(values) if values else 0.0

        bands = tuple(
            decibels(metadata.get(f"lavfi.astats.{index + 3}.RMS_level"), SPECTRUM_FLOOR)
            for index in range(len(SPECTRUM))
        )
        return cls(
            channels("RMS_level"),
            channels("Peak_level"),
            spectral("centroid"),
            spectral("flux"),
            bands if f"lavfi.astats.{len(SPECTRUM) + 2}.RMS_level" in metadata else (),
        )

    @property
    def energy(self) -> float:
        """0 at -40 dB RMS or quieter, 1 at -6 dB; follows loudness, not raw amplitude."""
        # Mastered music mostly sits between -40 and -6 dB RMS; spread that range.
        loudest = max(self.rms, default=SILENCE)
        return clamp((loudest + 40) / 34, 0, 1)

    @property
    def brightness(self) -> float:
        """0 for dark, bass-heavy sound; 1 for bright, treble-heavy sound."""
        if self.centroid <= 0:
            return 0.0
        return clamp(math.log(self.centroid / 200) / math.log(8000 / 200), 0, 1)


@dataclass
class Reaction:
    """Smooths levels into motion: speed from energy, light from brightness, sparks on hits."""

    energy: float = 0.0
    brightness: float = 0.0
    baseline: float = 0.0
    sparks: list[list[float]] = field(default_factory=list)  # [position 0..1, strength]
    spark_seed: int = 0
    bass: float = 0.0
    mid: float = 0.0
    treble: float = 0.0
    hit: float = 0.0
    pulse: float = 0.0
    pulse_target: float = 0.0
    measured: bool = False

    def feed(self, levels: Levels) -> None:
        self.measured = True
        self.energy += (levels.energy - self.energy) * 0.35
        self.brightness += (levels.brightness - self.brightness) * 0.2
        if levels.bands:
            # Bass below 200 Hz, mids to 2.5 kHz, treble above, scaled like the amp's bars.
            for name, low, high in (("bass", 0, 6), ("mid", 6, 14), ("treble", 14, 20)):
                band = levels.bands[low:high]
                loud = clamp((sum(band) / len(band) + 60) / 50, 0, 1)
                current = getattr(self, name)
                setattr(self, name, current + (loud - current) * 0.4)
        # An onset is spectral change well above its recent average.
        if levels.flux > self.baseline * 2.2 + 0.002 and levels.energy > 0.25:
            self.spark_seed = (self.spark_seed * 1103515245 + 12345) % 2**31
            self.sparks.append([(self.spark_seed % 1000) / 1000, min(1.0, levels.energy + 0.2)])
            del self.sparks[:-6]
            self.hit = 1.0
            self.pulse_target += 1.0
        self.baseline += (levels.flux - self.baseline) * 0.1

    def decay(self, seconds: float) -> None:
        for spark in self.sparks:
            spark[1] -= seconds * 2.5
        self.sparks = [spark for spark in self.sparks if spark[1] > 0]
        self.hit = max(0.0, self.hit - seconds * 3)
        # Glide toward the next ring step instead of jumping a whole step on a kick.
        self.pulse += (self.pulse_target - self.pulse) * min(1.0, seconds * 6)

    def quiet(self) -> None:
        self.energy = self.brightness = self.baseline = 0.0
        self.bass = self.mid = self.treble = self.hit = 0.0
        self.measured = False
        self.sparks.clear()

    @property
    def sound(self) -> Sound | None:
        """What patterns respond to, or None before any measurement (the saved drawing)."""
        if not self.measured:
            return None
        return Sound(self.bass, self.mid, self.treble, self.energy, self.hit, self.pulse)

    @property
    def rate(self) -> float:
        """Ribbon speed multiplier: slower in quiet passages, quicker when loud."""
        return 0.45 + 1.4 * self.energy
