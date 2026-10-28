# SPDX-License-Identifier: GPL-3.0-or-later
import asyncio
import base64
import io
import threading
import zlib

import pytest
from PIL import Image
from test_app import FakePlayer, populated
from textual.geometry import Region
from textual.widgets import Input
from textual_image.renderable import tgp

import kirlian_terminal.app as app_module
import kirlian_terminal.cover as cover_module
from kirlian_terminal.app import KirlianApp
from kirlian_terminal.cover import CoverImage
from kirlian_terminal.graphics import KittyImage


async def wait_for_native(widget):
    async with asyncio.timeout(5):
        while True:
            segments = rendered_segments(widget)
            if any(chr(0x10EEEE) in segment.text for segment in segments):
                return
            await asyncio.sleep(0.01)


@pytest.mark.parametrize("no_color", [False, True])
async def test_native_repaints_and_recent_covers_reuse_uploads_and_release_ids(
    monkeypatch, no_color
):
    from textual.app import App

    messages = native_renderer(monkeypatch)
    monkeypatch.setattr(KittyImage, "CACHE_SIZE", 2)

    class CoverApp(App):
        def compose(self):
            yield CoverImage("native", no_color=no_color)

    app = CoverApp()
    async with app.run_test(size=(100, 36)) as pilot:
        cover = app.query_one(CoverImage)
        # Cache reuse requires identical geometry. Let the initial square box
        # settle before rendering; the intentional resize is checked below.
        cover.fit(34, 17)
        await pilot.pause()
        first = Image.new("RGB", (300, 300), "red")
        cover.image = first
        await wait_for_native(cover.native)
        initial = [m["i"] for m in messages if m.get("a") == "t"]
        for _ in range(5):
            cover.native.refresh()
            await wait_for_native(cover.native)
        assert [m["i"] for m in messages if m.get("a") == "t"] == initial
        cover.image = Image.new("RGB", (300, 300), "blue")
        await wait_for_native(cover.native)
        assert len([m for m in messages if m.get("a") == "t"]) == 2
        cover.image = first
        await wait_for_native(cover.native)
        assert len([m for m in messages if m.get("a") == "t"]) == 2
        cover.fit(20, 10)
        await pilot.pause()
        await wait_for_native(cover.native)
        assert len([m for m in messages if m.get("a") == "t"]) == 3
        assert len([m for m in messages if m.get("a") == "d"]) == 1
        assert len(cover.native._images) == 2
        cover.image = None
        assert not cover.native._images
    uploaded = {m["i"] for m in messages if m.get("a") == "t"}
    deleted = [m["i"] for m in messages if m.get("a") == "d"]
    assert uploaded == set(deleted)
    assert len(deleted) == len(uploaded)


async def test_native_preparation_does_not_block_navigation_or_upload_stale_image(monkeypatch):
    from textual.app import App

    import kirlian_terminal.graphics as graphics

    messages = native_renderer(monkeypatch)
    encode = graphics.encode_pixels
    started, release = threading.Event(), threading.Event()

    def slow_encode(image):
        assert threading.current_thread() is not threading.main_thread()
        if image.getpixel((0, 0))[:3] == (255, 0, 0):
            started.set()
            release.wait(5)
        return encode(image)

    monkeypatch.setattr(graphics, "encode_pixels", slow_encode)

    class CoverApp(App):
        def compose(self):
            yield CoverImage("native")

    app = CoverApp()
    async with app.run_test(size=(100, 36)):
        cover = app.query_one(CoverImage)
        try:
            cover.image = Image.new("RGB", (300, 300), "red")
            async with asyncio.timeout(3):
                while not started.is_set():
                    rendered_segments(cover.native)
                    await asyncio.sleep(0.01)
            cover.image = Image.new("RGB", (300, 300), "blue")
            await wait_for_native(cover.native)
            release.set()
            await asyncio.sleep(0.1)
            assert len([m for m in messages if m.get("a") == "t"]) == 1
            encoded = "".join(m.get("payload", "") for m in messages)
            assert zlib.decompress(base64.b64decode(encoded))[:4] == bytes((0, 0, 255, 255))
        finally:
            release.set()


def rendered_segments(widget):
    return [
        segment
        for strip in widget.render_lines(Region(0, 0, widget.size.width, widget.size.height))
        for segment in strip
    ]


def native_renderer(monkeypatch):
    monkeypatch.setattr(cover_module, "image_widget", lambda **_: KittyImage)
    monkeypatch.setattr(app_module, "NATIVE_SUPPORTED", True)
    monkeypatch.setattr(cover_module, "NATIVE_SUPPORTED", True)
    messages = []
    monkeypatch.setattr(tgp, "_send_tgp_message", lambda **message: messages.append(message))
    return messages


@pytest.mark.parametrize("no_color", [False, True])
async def test_native_cover_keeps_exact_ids_through_terminal_output(
    tmp_path, audio_factory, monkeypatch, no_color
):
    monkeypatch.setenv("TERM_PROGRAM", "ghostty")
    monkeypatch.setenv("TERM", "xterm-256color")
    monkeypatch.delenv("COLORTERM", raising=False)
    monkeypatch.delenv("NO_COLOR", raising=False)
    if no_color:
        monkeypatch.setenv("NO_COLOR", "1")
    messages = native_renderer(monkeypatch)
    library, _ = populated(tmp_path, audio_factory)
    Image.new("RGB", (700, 700), (200, 30, 60)).save(tmp_path / "Music" / "cover.png")
    app = KirlianApp(library, player=FakePlayer())
    async with app.run_test(size=(120, 36)) as pilot:
        for _ in range(40):
            await pilot.pause(0.03)
            cover = app.query_one(CoverImage)
            if cover.image is not None:
                break
        assert cover.mode == "native"
        assert cover.image.size == (700, 700)
        await pilot.pause()
        assert app.console.color_system == "truecolor"
        for widget in (cover.renderer,):
            for _ in range(30):
                segments = rendered_segments(widget)
                placeholders = [s for s in segments if chr(0x10EEEE) in s.text]
                if placeholders:
                    break
                await pilot.pause(0.03)
            assert placeholders, (widget, widget.size, widget.image)
            triplet = placeholders[0].style.color.triplet
            image_id = triplet.red << 16 | triplet.green << 8 | triplet.blue
            assert any(m.get("U") == 1 and (m["i"] & 0xFFFFFF) == image_id for m in messages)
            output = io.StringIO()
            with app.console.capture() as capture:
                app.console.print(placeholders[0].text, style=placeholders[0].style, end="")
            output.write(capture.get())
            assert f"38;2;{triplet.red};{triplet.green};{triplet.blue}" in output.getvalue()
        pixel = cover.renderer.image.getpixel((0, 0))
        assert (pixel[0] == pixel[1] == pixel[2]) == no_color
        cover_id = next(m["i"] for m in reversed(messages) if m.get("U") == 1)
        await pilot.press("c")
        assert cover.mode == "blocks"
        assert cover.native.image is None
        assert any(m.get("a") == "d" for m in messages)
        assert all(m.get("d") == "I" and "i" in m for m in messages if m.get("a") == "d")
        await pilot.press("c")
        assert cover.mode == "native"
        assert cover_id is not None


async def test_cover_switch_preserves_selection_image_and_playback(
    tmp_path, audio_factory, monkeypatch
):
    native_renderer(monkeypatch)
    monkeypatch.delenv("NO_COLOR", raising=False)
    library, _ = populated(tmp_path, audio_factory)
    Image.new("RGB", (50, 50), "red").save(tmp_path / "Music" / "cover.png")
    player = FakePlayer()
    app = KirlianApp(library, player=player, artwork="blocks")
    async with app.run_test(size=(120, 36)) as pilot:
        for _ in range(40):
            await pilot.pause(0.03)
            cover = app.query_one(CoverImage)
            if cover.image is not None:
                break
        image = cover.image
        assert image is not None
        selection = app.selected()
        await pilot.press("c")
        assert cover.mode == "native"
        assert cover.native.image is image
        assert cover.blocks.image is None
        assert library.setting("artwork_mode") == "native"
        await pilot.press("c")
        assert cover.mode == "blocks"
        assert cover.blocks.image is image
        assert cover.native.image is None
        assert library.setting("artwork_mode") == "blocks"
        assert app.selected() == selection
        assert not player.calls
        await pilot.resize_terminal(80, 24)
        await pilot.resize_terminal(120, 36)
        await pilot.pause()
        assert cover.image is image
        assert cover.renderer.size.width > 0 and cover.renderer.size.height > 0
        await pilot.press("slash", "c")
        assert app.query_one("#search", Input).value == "c"
        assert cover.mode == "blocks"
        assert not player.calls
    assert KirlianApp(library, player=FakePlayer()).artwork_mode == "blocks"


def test_partial_protocol_support_uses_deliberate_fallback():
    from textual_image.widget import HalfcellImage, SixelImage

    from kirlian_terminal.graphics import automatic_renderer

    assert automatic_renderer(KittyImage, "WarpTerminal") is HalfcellImage
    assert automatic_renderer(KittyImage, "ghostty") is KittyImage
    assert automatic_renderer(KittyImage, "ghostty", "ghostty 1.3.1") is KittyImage
    assert automatic_renderer(KittyImage, "ghostty", "libghostty") is HalfcellImage
    assert automatic_renderer(KittyImage, "", "libghostty") is HalfcellImage
    assert automatic_renderer(KittyImage, "ghostty", "no reply") is KittyImage
    assert automatic_renderer(KittyImage, "kitty") is KittyImage
    assert automatic_renderer(SixelImage, "other") is SixelImage


async def test_basic_console_defaults_render_block_art_and_keep_music(
    tmp_path, audio_factory, monkeypatch
):
    from kirlian_terminal.visuals import Animation, Progress

    monkeypatch.setenv("TERM", "linux")
    monkeypatch.delenv("TERM_PROGRAM", raising=False)
    library, paths = populated(tmp_path, audio_factory)
    Image.new("RGB", (100, 100), "red").save(tmp_path / "Music" / "cover.png")
    player = FakePlayer()
    app = KirlianApp(library, player=player)
    async with app.run_test(size=(120, 36)) as pilot:
        cover = app.query_one(CoverImage)
        for _ in range(40):
            await pilot.pause(0.03)
            if cover.image is not None:
                break
        assert app.artwork_mode == "blocks"
        assert cover.image is not None
        assert cover.mode == "blocks"
        # Decode completion precedes the queued layout/paint messages.
        for _ in range(30):
            await pilot.pause(0.03)
            segments = rendered_segments(cover.renderer)
            if any("▀" in segment.text for segment in segments):
                break
        assert any("▀" in segment.text for segment in segments), (
            cover.size,
            cover.renderer.size,
            cover.display,
            cover.renderer.display,
            cover.renderer.image,
            segments,
        )
        assert app.query_one(Animation).render().plain.isascii()
        assert app.query_one(Progress).render().plain.isascii()
        await pilot.resize_terminal(80, 24)
        await pilot.press("enter", "enter")
        await pilot.pause()
        assert player.calls == [("play", paths, 0)]


async def test_late_cover_keeps_aspect_ratio_and_nonzero_drawing_area(monkeypatch):
    from textual.app import App
    from textual_image._terminal import CellSize

    monkeypatch.setattr(cover_module, "get_cell_size", lambda: CellSize(10, 20))

    class CoverApp(App):
        def compose(self):
            yield CoverImage("blocks")

    app = CoverApp()
    async with app.run_test(size=(80, 24)) as pilot:
        cover = app.query_one(CoverImage)
        cover.display = False
        cover.fit(32, 17)
        await pilot.pause()
        for width, height in ((300, 600), (600, 300), (600, 600)):
            cover.image = Image.new("RGB", (width, height), "red")
            cover.display = True
            await pilot.pause()
            size = cover.renderer.size
            assert 0 < size.width <= 32 and 0 < size.height <= 17
            assert abs(size.width * 10 / (size.height * 20) - width / height) < 0.05
            assert any("▀" in s.text for s in rendered_segments(cover.renderer))
            cover.display = False
            cover.image = None
            await pilot.pause()
