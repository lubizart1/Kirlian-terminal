# SPDX-License-Identifier: GPL-3.0-or-later
import asyncio
import threading
from dataclasses import replace

import pytest
from PIL import Image
from test_app import FakePlayer, populated
from textual.widgets import DataTable

import kirlian_terminal.app as app_module
from kirlian_terminal.app import KirlianApp, PlayerUpdate
from kirlian_terminal.palette import extract_palette, rgb
from kirlian_terminal.playback import PlaybackState
from kirlian_terminal.visuals import Animation


def luminance(color):
    channels = [channel / 255 for channel in rgb(color)]
    values = [
        channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4
        for channel in channels
    ]
    return sum(
        weight * value for weight, value in zip((0.2126, 0.7152, 0.0722), values, strict=True)
    )


@pytest.mark.parametrize("color", ["red", "blue", "#002900", "black", "white"])
def test_colors_preserve_hue_and_remain_readable(color):
    image = Image.new("RGB", (200, 100), color)
    before = image.tobytes()
    colors = extract_palette(image)
    assert colors == extract_palette(image)
    assert len(colors) == 1
    assert image.tobytes() == before
    assert (luminance(colors[0]) + 0.05) / (luminance("#121114") + 0.05) >= 4.5
    result = rgb(colors[0])
    original = image.getpixel((0, 0))
    assert result.index(max(result)) == original.index(max(original))
    if color in {"black", "white"}:
        assert result[0] == result[1] == result[2]


def test_multiple_substantial_colors_and_missing_cover():
    image = Image.new("RGB", (90, 30), "red")
    image.paste("blue", (30, 0, 60, 30))
    image.paste("green", (60, 0, 90, 30))
    colors = extract_palette(image)
    assert len(colors) == 3
    assert {rgb(color).index(max(rgb(color))) for color in colors} == {0, 1, 2}
    assert extract_palette(None) == ()


async def until_palette(pilot, animation):
    for _ in range(50):
        await pilot.pause(0.03)
        if animation.album_colors:
            return
    pytest.fail("Album palette did not arrive")


async def test_playing_album_drives_palette_with_hidden_art_and_survives_preferences(
    tmp_path, audio_factory
):
    library, paths = populated(tmp_path, audio_factory)
    root = tmp_path / "Music"
    other = audio_factory(
        root / "Other" / "other.wav", title="Other song", album="Other", artist="Other"
    )
    Image.new("RGB", (80, 80), "red").save(root / "cover.png")
    Image.new("RGB", (80, 80), "blue").save(other.parent / "cover.png")
    library.scan(root, lambda _: None, threading.Event())
    player = FakePlayer()
    app = KirlianApp(library, player=player, artwork="off", characters="ascii")
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        player.state = PlaybackState(
            path=paths[0], idle=False, paused=True, started_serial=1, position=30, duration=90
        )
        app.on_player_update(PlayerUpdate(player.state))
        animation = app.query_one(Animation)
        await until_palette(pilot, animation)
        red = animation.album_colors
        assert rgb(red[0])[0] > rgb(red[0])[2]
        assert not app.query_one("#context").display
        frozen = animation.render().plain
        seed = animation.clock.variation
        app.query_one(DataTable).move_cursor(row=1)
        await pilot.pause()
        assert animation.album_colors == red
        app.appearance = replace(app.appearance, palette="amber", characters="dots")
        app.apply_appearance()
        assert animation.album_colors == red
        assert animation.clock.variation == seed
        assert animation.timer is None
        app.appearance = replace(app.appearance, characters="ascii")
        app.apply_appearance()
        assert animation.render().plain == frozen
        player.state = replace(player.state, path=str(other), started_serial=2)
        app.on_player_update(PlayerUpdate(player.state))
        await until_palette(pilot, animation)
        assert rgb(animation.album_colors[0])[2] > rgb(animation.album_colors[0])[0]
        assert not player.calls
        app.on_player_update(PlayerUpdate(replace(player.state, idle=True)))
        assert animation.album_colors == ()


async def test_stale_palette_cannot_recolor_new_track(tmp_path, audio_factory, monkeypatch):
    library, paths = populated(tmp_path, audio_factory)
    root = tmp_path / "Music"
    other = audio_factory(root / "Other" / "other.wav", album="Other", artist="Other")
    library.scan(root, lambda _: None, threading.Event())
    started, release, returned = threading.Event(), threading.Event(), threading.Event()

    def slow_artwork(source):
        if str(other) in source:
            return Image.new("RGB", (20, 20), "blue")
        started.set()
        release.wait(10)
        returned.set()
        return Image.new("RGB", (20, 20), "red")

    monkeypatch.setattr(app_module, "load_artwork", slow_artwork)
    app = KirlianApp(library, player=FakePlayer(), artwork="off")
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        animation = app.query_one(Animation)
        state = PlaybackState(path=paths[0], idle=False, paused=True, started_serial=1)
        app.on_player_update(PlayerUpdate(state))
        try:
            for _ in range(50):
                await pilot.pause(0.03)
                if started.is_set():
                    break
            assert started.is_set()
            app.on_player_update(PlayerUpdate(replace(state, path=str(other), started_serial=2)))
            await until_palette(pilot, animation)
            blue = animation.album_colors
            assert rgb(blue[0])[2] > rgb(blue[0])[0]
        finally:
            release.set()
        # The stale palette has really been computed before checking it changed nothing.
        assert await asyncio.to_thread(returned.wait, 5)
        await pilot.pause(0.1)
        assert animation.album_colors == blue
