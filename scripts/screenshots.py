# SPDX-License-Identifier: GPL-3.0-or-later
"""Render README screenshots of the real app, using a generated demo library.

uv run python scripts/screenshots.py

Everything shown is generated here: album names, cover art, and silent audio, so
no personal or copyrighted music ends up in the repository. The player is driven
headlessly with sample levels; nothing plays aloud.
"""

import asyncio
import math
import os
import re
import struct
import sys
import tempfile
import threading
import wave
from pathlib import Path

from mutagen.id3 import APIC, TALB, TDRC, TIT2, TPE1, TRCK
from mutagen.wave import WAVE
from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent.parent / "docs" / "images"
ALBUMS = {
    ("Night Garden", "Lumen Choir", "2021"): (
        ["Moth Light", "Slow Bloom", "Glass Orchard", "Under Ferns", "Dew Line", "Afterglow"],
        ((34, 46, 92), (196, 120, 168)),
    ),
    ("Salt Flats", "Mara Ode", "2019"): (
        ["Horizon Hum", "White Field", "Mirage", "Last Bus Home"],
        ((214, 186, 140), (64, 92, 120)),
    ),
}


def cover(colors: tuple, seed: int) -> bytes:
    """A soft gradient with circles: abstract art made for the screenshots."""
    top, bottom = colors
    image = Image.new("RGB", (600, 600))
    draw = ImageDraw.Draw(image)
    for y in range(600):
        mix = y / 599
        color = tuple(round(a + (b - a) * mix) for a, b in zip(top, bottom, strict=True))
        draw.line([(0, y), (600, y)], color)
    for n in range(7):
        x, y = 90 + (n * 137 + seed * 61) % 420, 90 + (n * 89 + seed * 43) % 420
        r = 24 + (n * 29 + seed) % 70
        tone = tuple(min(255, c + 70) for c in bottom)
        draw.ellipse([x - r, y - r, x + r, y + r], outline=tone, width=6)
    from io import BytesIO

    data = BytesIO()
    image.save(data, "JPEG", quality=92)
    return data.getvalue()


def track(path: Path, title: str, album: str, artist: str, year: str, number: int, art: bytes):
    seconds = 150 + (number * 47) % 160
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(8000)
        audio.writeframes(struct.pack("<h", 0) * 8000 * seconds)
    tags = WAVE(path)
    tags.add_tags()
    for frame in (
        TIT2(encoding=3, text=[title]),
        TALB(encoding=3, text=[album]),
        TPE1(encoding=3, text=[artist]),
        TDRC(encoding=3, text=[year]),
        TRCK(encoding=3, text=[str(number)]),
        APIC(encoding=3, mime="image/jpeg", type=3, data=art),
    ):
        tags.tags.add(frame)
    tags.save()


def tidy(svg: str) -> str:
    """Offline fonts and an explicit size, so GitHub shows the image as rendered."""
    svg = re.sub(r"\s*@font-face\s*\{.*?\}", "", svg, flags=re.DOTALL)
    svg = svg.replace("Fira Code, monospace", "Menlo, Consolas, DejaVu Sans Mono, monospace")
    box = re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', svg)
    return svg.replace("<svg ", f'<svg width="{box[1]}" height="{box[2]}" ', 1)


async def shoot(data: Path, name: str, appearance: dict, theme: str = "") -> None:
    from kirlian_terminal.app import KirlianApp, PlayerUpdate
    from kirlian_terminal.appearance import Appearance
    from kirlian_terminal.audio import SPECTRUM, Levels
    from kirlian_terminal.library import Library
    from kirlian_terminal.playback import PlaybackState

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tests"))
    from test_app import FakePlayer  # A recording stand-in for mpv: nothing plays.

    library = Library(data / "library.sqlite3")
    if theme:
        (data / "themes").mkdir(exist_ok=True)
        (data / "themes" / "deep-sea.toml").write_text(theme)
    Appearance(**appearance).save(library)
    library.set_setting("amp", '{"visible": true}')
    app = KirlianApp(library, player=FakePlayer(), artwork="blocks", characters="dots")
    async with app.run_test(size=(148, 44)) as pilot:
        while not app.ready:
            await pilot.pause(0.05)
        album = next(a for a in app.albums if a.title == "Night Garden")
        app.query_one("DataTable").move_cursor(row=[r.value for r in app.rows].index(album.id))
        await pilot.press("enter")
        await pilot.pause(0.3)
        playing = album.tracks[1]
        queue = [{"filename": t.path, "id": n} for n, t in enumerate(album.tracks)]
        state = PlaybackState(
            path=playing.path,
            index=1,
            idle=False,
            paused=False,
            started_serial=1,
            position=92,
            duration=playing.duration,
            playlist=queue,
            volume=65,
            codec="flac",
            bitrate=912000,
            samplerate=44100,
            channels=2,
        )
        app.player.state = state
        app.on_player_update(PlayerUpdate(state))
        app.query_one("DataTable").move_cursor(row=1)
        for step in range(40):
            bands = tuple(
                -16 - abs(i - 6) * 1.6 + 4 * math.sin(step / 3 + i) for i in range(len(SPECTRUM))
            )
            levels = Levels(rms=(-13.0, -15.0), peak=(-5.0, -6.0), bands=bands, flux=0.05)
            for panel in app.query("AmpPanel"):
                if panel.display:
                    panel.measure(levels)
            app.query_one("Animation").react(levels)
            await pilot.pause(0.05)
        await pilot.pause(0.5)
        (OUT / f"{name}.svg").write_text(tidy(app.export_screenshot(title="Kirlian Terminal")))
        print(OUT / f"{name}.svg")


async def main() -> None:
    os.environ.pop("NO_COLOR", None)
    os.environ.setdefault("COLORTERM", "truecolor")
    OUT.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp())
    for seed, ((album, artist, year), (songs, colors)) in enumerate(ALBUMS.items()):
        folder = root / "Music" / album
        folder.mkdir(parents=True)
        art = cover(colors, seed)
        for number, title in enumerate(songs, 1):
            track(folder / f"{number:02d} {title}.wav", title, album, artist, year, number, art)
    deep_sea = (
        'name = "Deep sea"\naccent = "#ff6ac1"\nselection = "#16406b"\ntext = "#d8f3ff"\n'
        'muted = "#7fa7c4"\nfaint = "#24496b"\nedge = "#1d3d5c"\nbackground = "#071726"\n'
        'panel = "#0d2238"\ndialog = "#0a1c30"\nwarning = "#ffb347"\n'
    )
    shots = [
        ("player", {"amp": "record"}, ""),
        ("deep-sea-theme", {"palette": "custom-deep-sea", "amp": "playback"}, deep_sea),
    ]
    from kirlian_terminal.library import Library

    for name, appearance, theme in shots:
        data = root / name
        data.mkdir()
        Library(data / "library.sqlite3").scan(root / "Music", lambda _: None, threading.Event())
        await shoot(data, name, appearance, theme)


if __name__ == "__main__":
    asyncio.run(main())
