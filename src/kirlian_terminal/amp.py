# SPDX-License-Identifier: GPL-3.0-or-later
"""The amp: live level meters, a ten-band equalizer, preamp, balance, ReplayGain.

The panel only draws and forwards keys; the app owns the settings and tells mpv.
Columns run PRE, the ten bands, then BAL, matching left/right selection.
"""

from __future__ import annotations

import time

from rich.text import Text
from textual.binding import Binding
from textual.widgets import Static

from . import i18n
from .appearance import INK, QUIET
from .audio import BANDS, GAIN_LIMIT, SILENCE, AmpSettings, Levels
from .i18n import _
from .playback import PlaybackState

COLUMNS = len(BANDS) + 2  # PRE, bands, BAL
SLIDER_ROWS = 7  # +12 … -12 dB in 4 dB steps
WARM = "#e2a895"
DIM = "#4f4752"


def band_label(frequency: int) -> str:
    return f"{frequency // 1000}k" if frequency >= 1000 else str(frequency)


def gain_text(value: float) -> str:
    return f"{value:+.0f} dB"


def balance_text(value: float) -> str:
    if abs(value) < 0.05:
        return _("center")
    side = _("left") if value < 0 else _("right")
    return f"{side} {abs(value) * 100:.0f}%"


class AmpPanel(Static, can_focus=True):
    """Draws the amp; its keys work while it has focus."""

    BINDINGS = [
        Binding("left,h", "choose(-1)", show=False),
        Binding("right,l", "choose(1)", show=False),
        Binding("up,k", "adjust(1)", show=False),
        Binding("down,j", "adjust(-1)", show=False),
        Binding("0", "reset", show=False),
        Binding("e", "equalizer", show=False),
        Binding("comma", "preset(-1)", show=False),
        Binding("full_stop", "preset(1)", show=False),
        Binding("g", "replaygain", show=False),
        Binding("escape,w", "close", show=False),
    ]

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.settings = AmpSettings()
        self.state = PlaybackState()
        self.levels = Levels()
        self.column = 6  # 1 kHz
        self.accent = INK
        self.ascii = False
        self.compact = False
        self.hold = [SILENCE, SILENCE]
        self.held_at = [0.0, 0.0]

    # Keys are forwarded to the app, which owns settings and playback.
    def action_choose(self, step: int) -> None:
        self.column = (self.column + step) % COLUMNS
        self.refresh()

    def action_adjust(self, step: int) -> None:
        self.app.amp_adjust(self.column, step)

    def action_reset(self) -> None:
        self.app.amp_adjust(self.column, None)

    def action_equalizer(self) -> None:
        self.app.amp_toggle_equalizer()

    def action_preset(self, step: int) -> None:
        self.app.amp_preset(step)

    def action_replaygain(self) -> None:
        self.app.amp_replaygain()

    def action_close(self) -> None:
        self.app.action_amp()

    def show(self, settings: AmpSettings) -> None:
        self.settings = settings
        self.refresh()

    def observe(self, state: PlaybackState) -> None:
        self.state = state
        if state.paused or state.idle:
            self.levels = Levels()
        self.refresh()

    def measure(self, levels: Levels) -> None:
        """Peak marks hold for a second, then fall 20 dB per second."""
        now = time.monotonic()
        for channel in (0, 1):
            peak = levels.peak[channel] if channel < len(levels.peak) else SILENCE
            if peak >= self.hold[channel]:
                self.hold[channel], self.held_at[channel] = peak, now
            elif now - self.held_at[channel] > 1:
                fall = (now - self.held_at[channel] - 1) * 20
                self.hold[channel] = max(peak, self.hold[channel] - fall)
        self.levels = levels
        self.refresh()

    def render(self) -> Text:
        width = max(40, self.size.width)
        text = Text()
        self.info_line(text, width)
        text.append("\n\n")
        meter_width = max(10, min(36, width // 2 - 22))
        left = [
            self.meter(_("L"), 0, meter_width),
            self.meter(_("R"), 1, meter_width),
            Text(),
            self.balance(meter_width),
            self.replaygain_line(),
        ]
        right = self.equalizer_rows()
        rows = max(len(left), len(right))
        gap = meter_width + 16
        for row in range(rows):
            line = left[row].copy() if row < len(left) else Text()
            line.pad_right(max(0, gap - line.cell_len))
            if row < len(right):
                line.append_text(right[row])
            text.append_text(line)
            text.append("\n")
        text.append_text(self.help_line())
        return text

    def info_line(self, text: Text, width: int) -> None:
        state = self.state
        parts = []
        if state.codec:
            parts.append(state.codec.upper().replace("PCM_", "PCM "))
        if state.bitrate:
            parts.append(_("{kbps} kbps", kbps=round(state.bitrate / 1000)))
        if state.samplerate:
            parts.append(_("{khz} kHz", khz=f"{state.samplerate / 1000:g}"))
        if state.channels:
            parts.append(
                _("mono")
                if state.channels == 1
                else _("stereo")
                if state.channels == 2
                else _("{n} channels", n=state.channels)
            )
        info = Text(" · ".join(parts) or _("Nothing playing"), QUIET)
        settings = self.settings
        status = Text()
        status.append(
            _("EQ on") if settings.enabled else _("EQ off"),
            f"bold {self.accent}" if settings.enabled else QUIET,
        )
        if settings.preset:
            status.append(f" · {i18n._(settings.preset)}", INK)
        elif settings.enabled:
            status.append(" · " + _("Custom"), INK)
        mode = {"no": _("off"), "track": _("track"), "album": _("album")}[settings.replaygain]
        status.append(" · " + _("ReplayGain: {mode}", mode=mode), QUIET)
        info.pad_right(max(1, width - info.cell_len - status.cell_len))
        text.append_text(info)
        text.append_text(status)

    def meter(self, label: str, channel: int, width: int) -> Text:
        level = self.levels.rms[channel] if channel < len(self.levels.rms) else SILENCE
        fill = round((level - SILENCE) / -SILENCE * width)
        hold = round((self.hold[channel] - SILENCE) / -SILENCE * (width - 1))
        clipping = self.hold[channel] >= -0.1
        line = Text(f"{label} ", QUIET)
        line.append("[" if self.ascii else "▕", DIM)
        for cell in range(width):
            loud = cell >= width * 0.85
            if cell == hold and self.hold[channel] > SILENCE:
                line.append("|" if self.ascii else "▌", WARM if loud else INK)
            elif cell < fill:
                line.append("#" if self.ascii else "█", WARM if loud else self.accent)
            else:
                line.append("." if self.ascii else "·", DIM)
        line.append("]" if self.ascii else "▏", DIM)
        reading = _("CLIP") if clipping else f"{level:.0f} dB" if level > SILENCE else "–"
        line.append(f" {reading}", WARM if clipping else QUIET)
        return line

    def balance(self, width: int) -> Text:
        selected = self.column == COLUMNS - 1
        line = Text(f"{_('BAL')} ", f"bold {self.accent}" if selected else QUIET)
        position = round((self.settings.balance + 1) / 2 * (width - 1))
        for cell in range(width):
            if cell == position:
                line.append("o" if self.ascii else "●", self.accent if selected else INK)
            else:
                line.append("-" if self.ascii else "─", DIM)
        line.append(f" {balance_text(self.settings.balance)}", QUIET)
        return line

    def replaygain_line(self) -> Text:
        mode = self.settings.replaygain
        line = Text(_("ReplayGain") + " ", QUIET)
        for value, label in (("no", _("off")), ("track", _("track")), ("album", _("album"))):
            line.append(f" {label} ", f"bold {self.accent}" if value == mode else DIM)
        return line

    def equalizer_rows(self) -> list[Text]:
        settings = self.settings
        values = [settings.preamp, *settings.gains]
        labels = [_("PRE"), *(band_label(f) for f in BANDS)]
        cell = 5
        rows: list[Text] = []
        if self.compact:
            bars = " ▁▂▃▄▅▆▇█" if not self.ascii else " .:-=+*#%"
            line = Text()
            for index, value in enumerate(values):
                level = round((value + GAIN_LIMIT) / (2 * GAIN_LIMIT) * (len(bars) - 1))
                style = (
                    f"bold {self.accent}"
                    if index == self.column
                    else (INK if settings.enabled else DIM)
                )
                line.append(bars[level].center(cell), style)
            rows.append(line)
        else:
            for row in range(SLIDER_ROWS):
                line = Text()
                for index, value in enumerate(values):
                    handle = round((GAIN_LIMIT - value) / (2 * GAIN_LIMIT) * (SLIDER_ROWS - 1))
                    selected = index == self.column
                    if row == handle:
                        mark, style = (
                            ("o" if self.ascii else "●"),
                            (self.accent if selected else INK if settings.enabled else QUIET),
                        )
                    else:
                        center = row == SLIDER_ROWS // 2
                        mark = ("+" if center else "|") if self.ascii else ("┼" if center else "│")
                        style = self.accent if selected else DIM
                    line.append(mark.center(cell), style)
                rows.append(line)
        names = Text()
        for index, label in enumerate(labels):
            names.append(
                label.center(cell), f"bold {self.accent}" if index == self.column else QUIET
            )
        rows.append(names)
        rows.append(self.readout())
        return rows

    def readout(self) -> Text:
        settings = self.settings
        if self.column == 0:
            name, value = _("Preamp"), gain_text(settings.preamp)
        elif self.column == COLUMNS - 1:
            name, value = _("Balance"), balance_text(settings.balance)
        else:
            frequency = BANDS[self.column - 1]
            name = (
                _("{hz} Hz", hz=band_label(frequency))
                if frequency < 1000
                else _("{khz} kHz", khz=frequency // 1000)
            )
            value = gain_text(settings.gains[self.column - 1])
        return Text.assemble(
            ("▸ " if not self.ascii else "> ", self.accent), (name, INK), "  ", (value, QUIET)
        )

    def help_line(self) -> Text:
        pairs = (
            ("←→", _("choose")),
            ("↑↓", _("adjust")),
            ("0", _("reset")),
            ("e", _("EQ on/off")),
            (", .", _("presets")),
            ("g", _("ReplayGain")),
            ("w", _("close")),
        )
        line = Text()
        for index, (key, label) in enumerate(pairs):
            if index:
                line.append("   ")
            line.append(key, self.accent)
            line.append(f" {label}", QUIET)
        return line
