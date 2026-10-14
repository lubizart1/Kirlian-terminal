"""A continuous filament and a separate, truthful playback progress line."""

from __future__ import annotations

import time

from rich.text import Text
from textual.timer import Timer
from textual.widgets import Static

from .animations import AnimationClock, Variation
from .appearance import INK, Appearance
from .palette import mix, ribbon_color
from .playback import PlaybackState


class Animation(Static):
    def __init__(self, enabled: bool = True, **kwargs):
        super().__init__(**kwargs)
        self.appearance = Appearance(motion="gentle" if enabled else "off")
        self.clock = AnimationClock()
        self.timer: Timer | None = None
        self.playing = False
        self.fraction = 0.0
        self.album_colors: tuple[str, ...] = ()
        self.color_key = None
        self.color_bands: list[tuple[str, str]] = []

    @property
    def enabled(self) -> bool:
        return self.appearance.motion != "off"

    def configure(self, appearance: Appearance) -> None:
        self.appearance = appearance
        self.clock.running(self.playing and appearance.motion == "gentle", time.monotonic())
        self.schedule()
        self.draw()

    def observe(self, state: PlaybackState) -> None:
        before = (self.playing, self.clock.serial, self.fraction)
        self.playing = not (state.paused or state.idle or state.loading)
        self.fraction = min(1, max(0, state.position / state.duration)) if state.duration else 0
        serial = state.started_serial if not state.loading and not state.idle else 0
        self.clock.observe(
            serial, self.playing and self.appearance.motion == "gentle", time.monotonic()
        )
        self.schedule()
        # The timer owns moving frames. Player position events only need a draw
        # for a state transition or a changed progress highlight while still.
        if before[:2] != (self.playing, self.clock.serial) or (
            self.timer is None and before[2] != self.fraction
        ):
            self.draw()

    def schedule(self) -> None:
        active = self.playing and self.appearance.motion == "gentle"
        if active and self.timer is None:
            self.timer = self.set_interval(0.1, self.draw)
        elif not active and self.timer is not None:
            self.timer.stop()
            self.timer = None

    def on_resize(self) -> None:
        self.draw()

    def draw(self) -> None:
        if not self.enabled:
            self.update(Text(""), layout=False)
            return
        width = max(1, self.size.width)
        frame = self.clock.variation.ribbon_frame(
            self.clock.time(time.monotonic()), width, self.appearance.characters
        )
        text = Text()
        played = int(self.fraction * width)
        colors = self.album_colors or (self.appearance.accent,)
        color_key = (colors, width, bool(self.album_colors))
        if color_key != self.color_key:
            self.color_key = color_key
            self.color_bands = []
            for start in range(0, width, 4):
                color = ribbon_color(colors, start / max(1, width - 1))
                highlight = mix(color, "#ffffff", 0.3) if self.album_colors else INK
                self.color_bands.append((color, highlight))
        for index, line in enumerate(frame.splitlines()):
            if index:
                text.append("\n")
            for band, start in enumerate(range(0, len(line), 4)):
                end = min(start + 4, len(line))
                split = max(start, min(end, played))
                color, highlight = self.color_bands[band]
                text.append(line[start:split], highlight)
                text.append(line[split:end], color)
        self.update(text, layout=False)

    def set_palette(self, colors: tuple[str, ...]) -> None:
        self.album_colors = colors
        self.draw()

    def select(self, variation: Variation) -> None:
        self.clock.select(variation, time.monotonic())
        self.draw()

    def shuffle(self) -> None:
        self.clock.shuffle(time.monotonic())
        self.draw()

    def on_unmount(self) -> None:
        if self.timer is not None:
            self.timer.stop()
            self.timer = None


class Progress(Static):
    fraction = 0.0
    ascii = False
    accent = Appearance().accent

    def set_progress(self, position: float, duration: float) -> None:
        before = int(self.fraction * self.size.width)
        self.fraction = min(1, max(0, position / duration)) if duration else 0
        if int(self.fraction * self.size.width) != before:
            self.refresh()

    def render(self) -> Text:
        width = max(1, self.size.width)
        filled = min(width - 1, int(self.fraction * width))
        return Text.assemble(
            (("-" if self.ascii else "─") * filled, INK),
            ("o" if self.ascii else "●", self.accent),
            (("-" if self.ascii else "─") * (width - filled - 1), "#49424c"),
        )
