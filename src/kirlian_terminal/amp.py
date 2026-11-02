# SPDX-License-Identifier: GPL-3.0-or-later
"""The amp: what is playing, drawn as frequency bars and level meters.

The panel only displays; it never takes keys, so the library keeps working while
it is open. Sound changes (equalizer, preamp, balance, ReplayGain) live in the
Sound screen, a plain list where up/down choose a row and left/right change it.
"""

from __future__ import annotations

import time

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import DataTable, Label, Static

from . import i18n
from .appearance import INK, QUIET
from .audio import (
    BANDS,
    GAIN_LIMIT,
    PREAMP_RANGE,
    SILENCE,
    SPECTRUM,
    AmpSettings,
    Levels,
    Tempo,
)
from .i18n import N_, _, n_
from .playback import PlaybackState

COLUMNS = len(BANDS) + 2  # Preamp, ten bands, balance: the app's adjustment targets.
WARM = "#e2a895"
DIM = "#4f4752"
EIGHTHS = " ▁▂▃▄▅▆▇█"
# Band levels map to bar height between these; music bands mostly sit inside.
BAR_FLOOR, BAR_CEILING = -60.0, -10.0
# From this width the level meters stand beside the spectrum instead of below it.
WIDE, METER_WIDTH = 70, 20
MINI_HEIGHT = 4  # Spectrum rows in the amp under the cover.


def frequency_label(frequency: int) -> str:
    if frequency >= 1000:
        value = frequency / 1000
        return f"{value:.0f}k" if value >= 10 or value.is_integer() else f"{value:.1f}k"
    return str(frequency)


def balance_text(value: float) -> str:
    if abs(value) < 0.05:
        return _("center")
    side = _("left") if value < 0 else _("right")
    return f"{side} {abs(value) * 100:.0f}%"


def replaygain_text(mode: str) -> str:
    return {"no": _("off"), "track": _("per track"), "album": _("per album")}[mode]


def speed_text(speed: float) -> str:
    return f"{speed:.2f}×"


def pitch_text(semitones: int) -> str:
    if semitones == 0:
        return _("original")
    return n_("{value} semitone", "{value} semitones", abs(semitones), value=f"{semitones:+d}")


def tempo_text(tempo: Tempo) -> str:
    parts = []
    if tempo.speed != 1.0:
        parts.append(_("speed {speed}", speed=speed_text(tempo.speed)))
    if tempo.semitones:
        parts.append(_("pitch {pitch}", pitch=pitch_text(tempo.semitones)))
    if tempo.tape:
        parts.append(_("tape"))
    return " · ".join(parts)


def equalizer_text(settings: AmpSettings) -> str:
    if not settings.enabled:
        return _("off")
    return i18n._(settings.preset) if settings.preset else _("Custom")


class AmpPanel(Static):
    """Frequency bars, left/right meters, and the file's format. Display only."""

    def __init__(self, mini: bool = False, **kwargs) -> None:
        super().__init__(**kwargs)
        # Mini: the small amp under the cover; settings, spectrum, and levels only.
        self.mini = mini
        self.settings = AmpSettings()
        self.tempo = Tempo()
        self.state = PlaybackState()
        self.levels = Levels()
        self.accent = INK
        self.ascii = False
        self.compact = False
        self.bars = [0.0] * len(SPECTRUM)
        self.caps = [0.0] * len(SPECTRUM)
        self.cap_age = [0.0] * len(SPECTRUM)
        self.hold = [SILENCE, SILENCE]
        self.held_at = [0.0, 0.0]
        self.last = time.monotonic()

    def show(self, settings: AmpSettings) -> None:
        self.settings = settings
        self.refresh()

    def observe(self, state: PlaybackState) -> None:
        self.state = state
        if state.paused or state.idle:
            self.levels = Levels()
        self.refresh()

    def measure(self, levels: Levels) -> None:
        """Bars rise at once and fall smoothly; caps and peak marks hold, then drop."""
        now = time.monotonic()
        elapsed, self.last = now - self.last, now
        targets = [
            min(1.0, max(0.0, (value - BAR_FLOOR) / (BAR_CEILING - BAR_FLOOR)))
            for value in levels.bands
        ] or [0.0] * len(SPECTRUM)
        for index, target in enumerate(targets):
            self.bars[index] = max(target, self.bars[index] - elapsed * 1.6)
            if self.bars[index] >= self.caps[index]:
                self.caps[index], self.cap_age[index] = self.bars[index], 0.0
            else:
                self.cap_age[index] += elapsed
                if self.cap_age[index] > 0.4:
                    self.caps[index] = max(self.bars[index], self.caps[index] - elapsed * 0.9)
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
        if self.mini:
            return self.render_mini(max(20, self.size.width))
        width = max(40, self.size.width)
        height = 3 if self.compact else 6
        text = Text()
        text.append_text(self.info_line(width))
        text.append("\n")
        if width < WIDE:
            # Narrow: the spectrum across, the level meters underneath.
            rows = self.spectrum(width, height)
            rows += [self.meter(_("L"), 0, width), self.meter(_("R"), 1, width)]
        else:
            # Wide: the spectrum fills the width; tall level meters stand beside it.
            rows = self.spectrum(width - METER_WIDTH, height)
            meters = self.tall_meters(height)
            for row, column in zip(rows, meters, strict=True):
                row.pad_right(width - METER_WIDTH - row.cell_len)
                row.append_text(column)
        for row in rows:
            text.append_text(row)
            text.append("\n")
        text.append_text(self.hint_line(width))
        return text

    def render_mini(self, width: int) -> Text:
        rows = [self.status_text(), *self.spectrum(width, MINI_HEIGHT)]
        rows += [self.meter(_("L"), 0, width), self.meter(_("R"), 1, width)]
        return Text("\n").join(rows)

    def tall_meters(self, height: int) -> list[Text]:
        """Left and right levels as vertical bars with a dB scale, readouts underneath."""
        rows = []
        for row in range(height):
            top = height - row  # In bar units from the floor.
            line = Text("  ")
            for channel in (0, 1):
                level = self.levels.rms[channel] if channel < len(self.levels.rms) else SILENCE
                filled = (level - SILENCE) / -SILENCE * height
                fill = min(8, max(0, round((filled - (top - 1)) * 8)))
                held = (self.hold[channel] - SILENCE) / -SILENCE * height
                loud = top > height * 0.8
                if fill:
                    cells = " .:-=+*#%" if self.ascii else EIGHTHS
                    line.append(cells[fill] * 4, WARM if loud else self.accent)
                elif self.hold[channel] > SILENCE and top - 1 <= held < top:
                    line.append(("-" if self.ascii else "▔") * 4, WARM if loud else INK)
                else:
                    line.append(("." if self.ascii else "·").center(4), DIM)
                line.append(" ")
            scale = {0: "0", height // 2: f"{SILENCE / 2:.0f}", height - 1: f"{SILENCE:.0f}"}
            line.append(f" {scale.get(row, '')}", QUIET)
            rows.append(line)
        readouts = Text("  ")
        for channel, label in ((0, _("L")), (1, _("R"))):
            level = self.levels.rms[channel] if channel < len(self.levels.rms) else SILENCE
            clipping = self.hold[channel] >= -0.1 and self.settings.enabled
            reading = _("CLIP") if clipping else f"{level:.0f}" if level > SILENCE else "–"
            readouts.append(f"{label} ", QUIET)
            readouts.append(f"{reading:<5}"[:5], WARM if clipping else INK)
            readouts.append(" ")
        rows.append(readouts)
        return rows

    def info_line(self, width: int) -> Text:
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
        status = self.status_text()
        if info.cell_len + status.cell_len + 3 > width:
            # Too long for one line: the settings get their own, right-aligned.
            if status.cell_len <= width:
                status.align("right", width)  # Longer than the panel: let it wrap instead.
            info.append("\n")
        else:
            info.pad_right(width - info.cell_len - status.cell_len)
        info.append_text(status)
        return info

    def status_text(self) -> Text:
        settings = self.settings
        status = Text.assemble(
            (_("Equalizer") + " ", QUIET),
            (equalizer_text(settings), f"bold {self.accent}" if settings.enabled else INK),
            ("   " + _("ReplayGain") + " ", QUIET),
            (replaygain_text(settings.replaygain), INK),
        )
        # Preamp and balance only act while the equalizer is on; show them whenever they
        # do, so a changed sound is never invisible.
        if settings.enabled and settings.preamp:
            status.append("   " + _("Preamp") + " ", QUIET)
            status.append(f"{settings.preamp:+g} dB", f"bold {self.accent}")
        if settings.enabled and abs(settings.balance) >= 0.05:
            status.append("   " + _("Balance") + " ", QUIET)
            status.append(balance_text(settings.balance), f"bold {self.accent}")
        if not self.tempo.normal:
            status.append("   " + tempo_text(self.tempo), f"bold {self.accent}")
        return status

    def spectrum(self, width: int, height: int) -> list[Text]:
        count = len(SPECTRUM)
        bar = max(1, min(8, (width - count) // count))
        rows: list[Text] = []
        cells = EIGHTHS if not self.ascii else " .:-=+*#%"
        for row in range(height):
            line = Text()
            top = height - row  # In bar units from the floor.
            for index in range(count):
                level = self.bars[index] * height
                fill = min(8, max(0, round((level - (top - 1)) * 8)))
                # The falling cap sits in the first empty cell above the bar.
                cap_row = min(height, int(self.caps[index] * height) + 1)
                if fill > 0:
                    style = WARM if top == height and fill >= 6 else self.accent
                    mark = cells[fill]
                elif self.caps[index] > self.bars[index] + 0.04 and top == cap_row:
                    mark, style = ("-" if self.ascii else "─"), INK
                else:
                    mark, style = " ", DIM
                line.append(mark * bar, style)
                line.append(" ")
            rows.append(line)
        # Every third band is labelled where its whole label fits, never cut short.
        slots = [" "] * (count * (bar + 1))
        for index in range(0, count, 3):
            label = frequency_label(SPECTRUM[index])
            start = index * (bar + 1)
            if start + len(label) < len(slots) and all(
                c == " " for c in slots[start : start + len(label) + 1]
            ):
                slots[start : start + len(label)] = label
        rows.append(Text("".join(slots).rstrip(), QUIET))
        return rows

    def meter(self, label: str, channel: int, width: int) -> Text:
        level = self.levels.rms[channel] if channel < len(self.levels.rms) else SILENCE
        size = max(10, min(width - 14, len(SPECTRUM) * (max(1, min(4, (width - 20) // 20)) + 1)))
        fill = round((level - SILENCE) / -SILENCE * size)
        hold = round((self.hold[channel] - SILENCE) / -SILENCE * (size - 1))
        # Mastered music often peaks at full scale; only warn when our boosts could clip.
        clipping = self.hold[channel] >= -0.1 and self.settings.enabled
        line = Text(f"{label} ", QUIET)
        for cell in range(size):
            loud = cell >= size * 0.85
            if cell == hold and self.hold[channel] > SILENCE:
                line.append("|" if self.ascii else "▌", WARM if loud else INK)
            elif cell < fill:
                line.append("=" if self.ascii else "━", WARM if loud else self.accent)
            else:
                line.append("-" if self.ascii else "─", DIM)
        reading = _("CLIP") if clipping else f"{level:.0f} dB" if level > SILENCE else "–"
        line.append(f" {reading}", WARM if clipping else QUIET)
        return line

    def hint_line(self, width: int) -> Text:
        sound = (
            _("sound: equalizer, balance, ReplayGain, speed, pitch")
            if width >= WIDE
            else _("sound")
        )
        return Text.assemble(
            ("E", self.accent),
            (" " + sound + "   ", QUIET),
            ("w", self.accent),
            (" " + _("hide"), QUIET),
        )


# Sound screen rows: (id, label). Bands follow, one row each.
SETTINGS_ROWS = (
    ("enabled", N_("Equalizer")),
    ("preset", N_("Preset")),
    ("preamp", N_("Preamp")),
    ("balance", N_("Balance")),
    ("replaygain", N_("ReplayGain")),
    ("speed", N_("Speed")),
    ("pitch", N_("Pitch")),
    ("tape", N_("Tape")),
)
BAND_ROLES = (
    N_("deep rumble you feel more than hear"),
    N_("weight of bass and kick drum"),
    N_("punch of bass lines and drums"),
    N_("warmth; too much sounds muddy"),
    N_("body of voices and instruments"),
    N_("presence: voices step forward"),
    N_("clarity and attack of notes"),
    N_("bite and edge; too much is harsh"),
    N_("air, cymbals, and s sounds"),
    N_("sparkle at the very top"),
)


class SoundSettings(ModalScreen[None]):
    """One row per control: up/down choose, left/right change, Enter turns the EQ on/off."""

    BINDINGS = [
        Binding("escape,E", "close", "Close"),
        Binding("left,h", "change(-1)", "Less", show=False),
        Binding("right,l", "change(1)", "More", show=False),
        Binding("enter", "toggle", "On/off", priority=True),
        Binding("0", "reset", "Reset", show=False),
        Binding("R", "reset_all", "Reset all", show=False),
        Binding("j", "cursor(1)", "Down", show=False),
        Binding("k", "cursor(-1)", "Up", show=False),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.row_ids = [row for row, _label in SETTINGS_ROWS] + [
            f"band{index}" for index in range(len(BANDS))
        ]

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog", id="sound-settings"):
            yield Label(_("Sound"))
            yield Static(
                _(
                    "Changes apply to what is playing right away. Equalizer, balance, and "
                    "ReplayGain are remembered; speed and pitch reset next time. Your music "
                    "files are never changed, and with everything off you hear each file "
                    "exactly as it is."
                ),
                classes="dialog-hint",
            )
            yield DataTable(id="sound-rows", cursor_type="row", zebra_stripes=False)
            yield Static("", id="sound-detail")
            yield Static("", id="sound-keys")

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.add_column(_("Setting"), width=14)
        table.add_column(_("Value"))
        self.show(self.app.amp)
        table.focus()

    @property
    def row(self) -> str:
        return self.row_ids[max(0, self.query_one(DataTable).cursor_row)]

    def show(self, settings: AmpSettings) -> None:
        table = self.query_one(DataTable)
        position = table.cursor_row
        table.clear()
        accent = self.app.appearance.accent
        ascii = self.app.appearance.characters == "ascii"
        for row_id, label in SETTINGS_ROWS:
            table.add_row(
                Text(i18n._(label), QUIET), self.value(row_id, settings, accent), key=row_id
            )
        for index, frequency in enumerate(BANDS):
            gain = settings.gains[index]
            table.add_row(
                Text(_("{hz} Hz", hz=frequency_label(frequency)), QUIET),
                self.slider(gain, GAIN_LIMIT, settings.enabled, accent, ascii),
                key=f"band{index}",
            )
        table.move_cursor(row=max(0, position))
        self.describe(settings)

    def value(self, row_id: str, settings: AmpSettings, accent: str) -> Text:
        if row_id == "enabled":
            on = settings.enabled
            return Text(_("on") if on else _("off"), f"bold {accent}" if on else INK)
        if row_id == "preset":
            return Text.assemble(
                ("‹ ", QUIET),
                (
                    equalizer_text(settings)
                    if settings.enabled
                    else i18n._(settings.preset)
                    if settings.preset
                    else _("Custom"),
                    INK,
                ),
                (" ›", QUIET),
            )
        if row_id == "preamp":
            return Text(f"{settings.preamp:+.0f} dB", INK)
        if row_id == "balance":
            return Text(balance_text(settings.balance), INK)
        tempo = self.app.tempo
        if row_id == "speed":
            return Text(speed_text(tempo.speed), f"bold {accent}" if tempo.speed != 1 else INK)
        if row_id == "pitch":
            return Text(pitch_text(tempo.semitones), f"bold {accent}" if tempo.semitones else INK)
        if row_id == "tape":
            return Text(
                _("on") if tempo.tape else _("off"), f"bold {accent}" if tempo.tape else INK
            )
        return Text(replaygain_text(settings.replaygain), INK)

    def slider(self, gain: float, limit: float, enabled: bool, accent: str, ascii: bool) -> Text:
        """−12 … 0 … +12 dB as a centered bar, so boosts and cuts read at a glance."""
        half = 12
        steps = round(abs(gain) / limit * half)
        line = Text()
        for cell in range(-half, half + 1):
            if cell == 0:
                line.append("|" if ascii else "┃", QUIET)
            elif (gain > 0 and 0 < cell <= steps) or (gain < 0 and -steps <= cell < 0):
                line.append("#" if ascii else "█", accent if enabled else QUIET)
            else:
                line.append("." if ascii else "·", DIM)
        line.append(f"  {gain:+.0f} dB", INK if enabled else QUIET)
        return line

    def describe(self, settings: AmpSettings) -> None:
        row = self.row
        accent = self.app.appearance.accent
        if row == "enabled":
            detail = _("Turns the equalizer and preamp on or off. Off means no processing at all.")
            keys = [("enter", _("turn on/off"))]
        elif row == "preset":
            detail = _("Ready-made shapes. Choosing one sets all ten bands; you can adjust after.")
            keys = [("← →", _("choose a preset"))]
        elif row == "preamp":
            detail = _("Lowers or raises everything before the bands. Lower it if CLIP appears.")
            keys = [("← →", _("1 dB")), ("0", _("reset"))]
        elif row == "balance":
            detail = _("Moves the sound toward the left or right speaker.")
            keys = [("← →", _("10%")), ("0", _("center"))]
        elif row == "replaygain":
            detail = _(
                "Evens out loudness using volume tags many files carry. Per album keeps "
                "the album's own quiet and loud songs."
            )
            keys = [("← →", _("off, per track, per album"))]
        elif row == "speed":
            detail = _(
                "Plays faster or slower without changing the key, unless Tape is on. "
                "Resets to normal next time you open Kirlian."
            )
            keys = [("← →", _("5% slower or faster")), ("0", _("normal"))]
        elif row == "pitch":
            detail = _(
                "Moves the key up or down in semitones without changing the speed. "
                "Resets to the original next time you open Kirlian."
            )
            keys = [("← →", _("1 semitone")), ("0", _("original"))]
        elif row == "tape":
            detail = _(
                "Links pitch to speed like a record or tape: slower sounds deeper, faster "
                "sounds higher. Try it with speed 0.85× for a slowed sound."
            )
            keys = [("enter ← →", _("turn on/off"))]
        else:
            index = int(row.removeprefix("band"))
            detail = _(
                "{hz} Hz: {role}.",
                hz=frequency_label(BANDS[index]),
                role=i18n._(BAND_ROLES[index]),
            )
            keys = [("← →", _("cut or boost 1 dB")), ("0", _("flat"))]
        keys += [("↑ ↓", _("choose a row")), ("R", _("reset all sound")), ("esc", _("close"))]
        self.query_one("#sound-detail", Static).update(Text(detail, INK))
        hints = Text()
        for index, (key, label) in enumerate(keys):
            hints.append("   " if index else "")
            hints.append(key, f"bold {accent}")
            hints.append(f" {label}", QUIET)
        self.query_one("#sound-keys", Static).update(hints)

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        event.stop()
        self.describe(self.app.amp)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        event.stop()

    def action_cursor(self, step: int) -> None:
        table = self.query_one(DataTable)
        table.move_cursor(row=table.cursor_row + step)

    def action_change(self, step: int) -> None:
        app, row = self.app, self.row
        if row == "enabled":
            app.amp_toggle_equalizer()
        elif row == "preset":
            app.amp_preset(step)
        elif row == "preamp":
            app.amp_adjust(0, step)
        elif row == "balance":
            app.amp_adjust(COLUMNS - 1, step)
        elif row == "replaygain":
            app.amp_replaygain(step)
        elif row in {"speed", "pitch", "tape"}:
            app.tempo_change(row, step)
        else:
            app.amp_adjust(int(row.removeprefix("band")) + 1, step)
        self.show(app.amp)

    def action_reset(self) -> None:
        row = self.row
        if row in {"speed", "pitch"}:
            self.app.tempo_change(row, None)
            self.show(self.app.amp)
            return
        targets = {"preamp": 0, "balance": COLUMNS - 1}
        if row in targets or row.startswith("band"):
            column = targets[row] if row in targets else int(row.removeprefix("band")) + 1
            self.app.amp_adjust(column, None)
            self.show(self.app.amp)

    def action_reset_all(self) -> None:
        self.app.reset_sound()
        self.show(self.app.amp)

    def action_toggle(self) -> None:
        if self.row == "tape":
            self.app.tempo_change("tape", 1)
        else:
            self.app.amp_toggle_equalizer()
        self.show(self.app.amp)

    def action_close(self) -> None:
        self.dismiss(None)


__all__ = ["AmpPanel", "COLUMNS", "PREAMP_RANGE", "SoundSettings"]
