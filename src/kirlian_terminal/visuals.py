# SPDX-License-Identifier: GPL-3.0-or-later
"""A filament that moves with the playing audio, and a truthful progress line.

The ribbon's speed follows loudness, its light follows the brightness of the
sound, and hits flash along it. All three come from levels mpv measures; when
they are unavailable the ribbon keeps its own steady motion.
"""

from __future__ import annotations

import time

from rich.text import Text
from textual import events
from textual.content import Content
from textual.message import Message
from textual.timer import Timer
from textual.widgets import Static

from .animations import AnimationClock, Variation
from .appearance import COLORS, Appearance
from .audio import Levels, Reaction
from .palette import mix, ribbon_color
from .patterns import Frame
from .playback import PlaybackState

TRANSITION = 0.7  # Seconds for one pattern to dissolve into the next.
NAME_IN, NAME_HOLD, NAME_GONE = 0.25, 1.2, 1.8  # Name letters arrive, hold, scatter.


def scatter(column: int, row: int, salt: int = 0) -> float:
    """A fixed pseudo-random order for each dot, 0 to 1, so dissolves look grainy."""
    value = (column * 73856093) ^ (row * 19349663) ^ (salt * 83492791)
    return ((value * 2654435761) % 4294967296) / 4294967296


def smooth(progress: float) -> float:
    progress = min(1.0, max(0.0, progress))
    return progress * progress * (3 - 2 * progress)


def dissolve(
    old: Frame, new: Frame, progress: float, characters: str
) -> tuple[list[str], list[list[float]]]:
    """Each dot switches from the old pattern to the new one at its own moment."""
    rows, depth = [], []
    old_rows, new_rows = old.text.splitlines(), new.text.splitlines()
    for row, (old_line, new_line) in enumerate(zip(old_rows, new_rows, strict=False)):
        line, line_depth = [], []
        for column, (before, after) in enumerate(zip(old_line, new_line, strict=False)):
            if characters == "ascii":
                fresh = scatter(column, row, 1) < progress
                line.append(after if fresh else before)
                source = new if fresh else old
                line_depth.append(source.depth[row][column])
                continue
            old_mask, new_mask = ord(before) - 0x2800, ord(after) - 0x2800
            mask = 0
            for bit in range(8):
                fresh = scatter(column, row * 8 + bit, 2) < progress
                mask |= (1 << bit) & (new_mask if fresh else old_mask)
            line.append(chr(0x2800 + mask))
            from_new = mask & new_mask
            line_depth.append(new.depth[row][column] if from_new else old.depth[row][column])
        rows.append("".join(line))
        depth.append(line_depth)
    return rows, depth


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
        self.column_colors: list[tuple[str, str]] = []
        self.outgoing: Variation | None = None
        self.outgoing_time = 0.0
        self.switched_at = 0.0
        self.reaction = Reaction()
        self.last_draw = time.monotonic()

    @property
    def enabled(self) -> bool:
        return self.appearance.motion != "off"

    def configure(self, appearance: Appearance) -> None:
        self.appearance = appearance
        if appearance.motion != "gentle":
            self.outgoing = None  # Still and Off: no dissolve in progress either.
        self.clock.running(self.playing and appearance.motion == "gentle", time.monotonic())
        self.schedule()
        self.draw()

    def react(self, levels: Levels) -> None:
        """Feed one measured frame; only moving ribbons respond."""
        if not (self.playing and self.appearance.motion == "gentle"):
            return
        self.reaction.feed(levels)
        self.clock.set_rate(self.reaction.rate, time.monotonic())

    def observe(self, state: PlaybackState) -> None:
        before = (self.playing, self.clock.serial, self.fraction)
        self.playing = not (state.paused or state.idle or state.loading)
        if not self.playing and before[0]:
            # Pausing freezes the frame, including a dissolve that was under way.
            self.outgoing = None
        if not self.playing:
            self.reaction.quiet()
            self.clock.set_rate(1.0, time.monotonic())
        self.fraction = min(1, max(0, state.position / state.duration)) if state.duration else 0
        serial = state.started_serial if not state.loading and not state.idle else 0
        now = time.monotonic()
        previous, elapsed = self.clock.variation, self.clock.time(now)
        self.clock.observe(serial, self.playing and self.appearance.motion == "gentle", now)
        if self.clock.variation != previous and self.playing:
            self.begin_transition(previous, elapsed)  # A new song reveals its pattern.
        self.schedule()
        # The timer owns moving frames. Player position events only need a draw
        # for a state transition or a changed progress highlight while still.
        if before[:2] != (self.playing, self.clock.serial) or (
            self.timer is None and before[2] != self.fraction
        ):
            self.draw()

    @property
    def transitioning(self) -> bool:
        return self.outgoing is not None and time.monotonic() - self.switched_at < NAME_GONE

    def begin_transition(self, outgoing: Variation, outgoing_time: float) -> None:
        """Dissolve from the old pattern and briefly show the new one's name."""
        if self.appearance.motion != "gentle":
            return  # Still and Off motion change patterns without movement.
        self.outgoing, self.outgoing_time = outgoing, outgoing_time
        self.switched_at = time.monotonic()
        self.schedule()

    def schedule(self) -> None:
        moving = self.playing and self.appearance.motion == "gentle"
        active = moving or self.transitioning
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
        now = time.monotonic()
        self.reaction.decay(now - self.last_draw)
        self.last_draw = now
        characters = self.appearance.characters
        sound = self.reaction.sound if self.playing else None
        frame = self.clock.variation.render(self.clock.time(now), width, characters, sound)
        rows = frame.text.splitlines()
        depth = [list(row) for row in frame.depth]
        since = now - self.switched_at
        if self.outgoing is not None and since < TRANSITION:
            old = self.outgoing.render(self.outgoing_time, width, characters, sound)
            rows, depth = dissolve(old, frame, smooth(since / TRANSITION), characters)
        name = self.name_overlay(since, width) if self.outgoing is not None else {}
        if self.outgoing is not None and since >= NAME_GONE:
            self.outgoing = None
            self.schedule()
        self.update(self.paint(rows, depth, name, width), layout=False)

    def name_overlay(self, since: float, width: int) -> dict[int, str]:
        """The new pattern's name on the middle row: letters arrive, hold, then scatter."""
        label = f"  {self.clock.variation.label}  "
        if since >= NAME_GONE or len(label) > width:
            return {}
        start = (width - len(label)) // 2
        cells = {}
        for index, character in enumerate(label):
            order = scatter(index, 0, 7)
            arrived = since >= NAME_IN * order
            remaining = since < NAME_HOLD + (NAME_GONE - NAME_HOLD) * order
            if arrived and remaining:
                cells[start + index] = character
        return cells

    def column_styles(self, width: int) -> list[tuple[str, str, str, str]]:
        """Per column: main, fine, played main, played fine. Blended cell by cell."""
        colors = self.album_colors or (self.appearance.accent,)
        key = (colors, width, bool(self.album_colors))
        if key != self.color_key:
            self.color_key = key
            self.column_colors = []
            for column in range(width):
                color = ribbon_color(colors, column / max(1, width - 1))
                highlight = mix(color, "#ffffff", 0.3) if self.album_colors else COLORS.text
                self.column_colors.append((color, highlight))
        reaction = self.reaction
        glow = reaction.brightness * 0.22
        styles = []
        for column, (color, highlight) in enumerate(self.column_colors):
            lift = glow
            center = (column + 0.5) / width
            for position, strength in reaction.sparks:
                distance = abs(center - position)
                if distance < 0.07:
                    lift += strength * 0.65 * (1 - distance / 0.07)
            if lift > 0.01:
                lift = min(0.85, lift)
                color, highlight = mix(color, "#ffffff", lift), mix(highlight, "#ffffff", lift)
            # Fine strands sit back: closer to the surface, so the main thread reads first.
            styles.append(
                (
                    color,
                    mix(color, COLORS.background, 0.45),
                    highlight,
                    mix(highlight, COLORS.background, 0.4),
                )
            )
        return styles

    def paint(
        self, rows: list[str], depth: list[list[float]], name: dict[int, str], width: int
    ) -> Text:
        styles = self.column_styles(width)
        played = int(self.fraction * width)
        text = Text()
        for index, line in enumerate(rows):
            if index:
                text.append("\n")
            run, run_style = [], None
            for column, character in enumerate(line[:width]):
                if index == 1 and column in name:
                    character, style = name[column], f"bold {COLORS.text}"
                else:
                    main, fine, played_main, played_fine = styles[column]
                    back = depth[index][column] < 1 if column < len(depth[index]) else False
                    if column < played:
                        style = played_fine if back else played_main
                    else:
                        style = fine if back else main
                if style != run_style and run:
                    text.append("".join(run), run_style)
                    run = []
                run.append(character)
                run_style = style
            if run:
                text.append("".join(run), run_style)
        return text

    def set_palette(self, colors: tuple[str, ...]) -> None:
        self.album_colors = colors
        self.draw()

    def select(self, variation: Variation) -> None:
        now = time.monotonic()
        previous, elapsed = self.clock.variation, self.clock.time(now)
        self.clock.select(variation, now)
        if variation != previous:
            self.begin_transition(previous, elapsed)
        self.draw()

    def shuffle(self) -> None:
        now = time.monotonic()
        previous, elapsed = self.clock.variation, self.clock.time(now)
        self.clock.shuffle(now)
        self.begin_transition(previous, elapsed)
        self.draw()

    def on_unmount(self) -> None:
        if self.timer is not None:
            self.timer.stop()
            self.timer = None


class Progress(Static):
    """The song's progress. Click to jump there, or drag and let go."""

    fraction = 0.0
    ascii = False
    accent = Appearance().accent
    dragging = False

    class Seek(Message):
        def __init__(self, fraction: float) -> None:
            super().__init__()
            self.fraction = fraction

    def set_progress(self, position: float, duration: float) -> None:
        if self.dragging:
            return  # The listener's hand wins until they let go.
        before = int(self.fraction * self.size.width)
        self.fraction = min(1, max(0, position / duration)) if duration else 0
        if int(self.fraction * self.size.width) != before:
            self.refresh()

    def point(self, x: int) -> float:
        return min(1.0, max(0.0, x / max(1, self.size.width - 1)))

    def on_mouse_down(self, event: events.MouseDown) -> None:
        self.dragging = True
        self.capture_mouse()
        self.fraction = self.point(event.x)
        self.refresh()

    def on_mouse_move(self, event: events.MouseMove) -> None:
        if self.dragging:
            self.fraction = self.point(event.x)
            self.refresh()

    def on_mouse_up(self, event: events.MouseUp) -> None:
        if self.dragging:
            self.dragging = False
            self.release_mouse()
            self.post_message(self.Seek(self.point(event.x)))

    def render(self) -> Text:
        width = max(1, self.size.width)
        filled = min(width - 1, int(self.fraction * width))
        return Text.assemble(
            (("-" if self.ascii else "─") * filled, COLORS.text),
            ("o" if self.ascii else "●", self.accent),
            (("-" if self.ascii else "─") * (width - filled - 1), COLORS.faint),
        )


class Transport(Static):
    """Clickable playback controls; each does what its key does."""

    def show(self, playing: bool, accent: str, ascii: bool) -> None:
        if ascii:
            glyphs = ("|<", "<<", "||" if playing else ">", ">>", ">|")
        else:
            glyphs = ("|◀", "◀◀", "❚❚" if playing else "▶", "▶▶", "▶|")
        actions = ("previous", "seek(-5)", "pause", "seek(5)", "next")
        content = Content("   ").join(
            Content.from_markup(
                f'[{accent if action == "pause" else COLORS.text} @click="app.{action}"]$glyph[/]',
                glyph=glyph,  # A variable, so a glyph like "[" can never read as markup.
            )
            for glyph, action in zip(glyphs, actions, strict=True)
        )
        if content != self.content:
            self.update(content)


VOWELS = set("aeiouyàáâäãåæèéêëìíîïòóôöõøùúûüýÿœ")
REST, WEAK, ACCENT = 0, 1, 2
RHYTHM_STEPS = 16
RHYTHM_STEP_SECONDS = 0.15


def rhythm(title: str) -> list[int]:
    """Turn a song title into a step pattern: one hit per syllable, a rest per word gap.

    Syllables are approximated by vowel groups; the first syllable of each word is
    accented, and every digit is its own hit. The pattern loops, capped at 16 steps.
    """
    steps: list[int] = []
    for word in title.casefold().split():
        hits = 0
        previous_vowel = False
        for char in word:
            if char.isdigit():
                hits += 1
                previous_vowel = False
            elif char.isalpha():
                vowel = char in VOWELS
                hits += vowel and not previous_vowel
                previous_vowel = vowel
        if any(c.isalnum() for c in word):
            hits = max(1, hits)
            steps += [ACCENT] + [WEAK] * (hits - 1) + [REST]
    return steps[:RHYTHM_STEPS] or [ACCENT, REST, WEAK, REST]


class TitleRhythm(Static):
    """Loading indicator: the playing title, read as a drum pattern with a walking playhead."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.steps: list[int] = []
        self.position = 0
        self.timer: Timer | None = None
        self.accent = COLORS.text
        self.ascii = False
        self.key: tuple = ()

    def play(self, title: str, accent: str, ascii: bool, moving: bool) -> None:
        key = (title, accent, ascii, moving)
        if key == self.key:
            return
        if not self.key or self.key[0] != title:
            self.steps = rhythm(title)
            self.position = 0
        self.key = key
        self.accent, self.ascii = accent, ascii
        if moving and self.timer is None:
            self.timer = self.set_interval(RHYTHM_STEP_SECONDS, self.advance)
        elif not moving:
            self.stop_timer()
        self.draw()

    def stop(self) -> None:
        self.stop_timer()
        self.key = ()

    def stop_timer(self) -> None:
        if self.timer is not None:
            self.timer.stop()
            self.timer = None

    def advance(self) -> None:
        self.position = (self.position + 1) % len(self.steps)
        self.draw()

    def draw(self) -> None:
        marks = (".", "x", "X") if self.ascii else ("·", "•", "●")
        moving = self.timer is not None
        text = Text()
        for index, step in enumerate(self.steps):
            if index:
                text.append(" ")
            if moving and index == self.position:
                style = f"bold {self.accent}"
            elif moving and index == (self.position - 1) % len(self.steps) and step:
                style = COLORS.text  # The last hit lingers for one step.
            else:
                style = COLORS.faint if step == REST else COLORS.muted
            text.append(marks[step], style)
        self.update(text, layout=False)

    def on_unmount(self) -> None:
        self.stop_timer()
