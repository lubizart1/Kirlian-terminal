# SPDX-License-Identifier: GPL-3.0-or-later
import pytest
from test_app import FakePlayer, populated
from textual.widgets import Select

from kirlian_terminal.app import KirlianApp
from kirlian_terminal.appearance import Appearance
from kirlian_terminal.brand import ASCII_MARK, Brand, drawn_wordmark


@pytest.fixture(autouse=True)
def desktop_terminal(monkeypatch):
    monkeypatch.setenv("TERM", "xterm-256color")


@pytest.mark.parametrize("artwork", ["native", "blocks", "off"])
async def test_character_brand_is_independent_of_artwork_and_resizes(
    tmp_path, audio_factory, artwork
):
    library, _ = populated(tmp_path, audio_factory)
    player = FakePlayer()
    app = KirlianApp(library, player=player, artwork=artwork)
    async with app.run_test(size=(120, 36)) as pilot:
        brand = app.query_one(Brand)
        await pilot.pause()
        assert brand.render().plain == drawn_wordmark()
        assert not brand.children
        assert len(drawn_wordmark().splitlines()) == 2
        assert all(len(row) <= brand.size.width for row in drawn_wordmark().splitlines())
        await pilot.resize_terminal(80, 24)
        assert brand.render().plain == "✳  kirlian"
        assert brand.size.height == 1
        await pilot.resize_terminal(80, 36)
        assert brand.render().plain == drawn_wordmark()
        assert brand.size.height == 2
        assert brand.region.right <= app.query_one("#search-hint").region.x
        assert not app.screen.show_horizontal_scrollbar
        assert not player.calls


async def test_wordmark_preferences_preview_cancel_and_persist(tmp_path, audio_factory):
    library, _ = populated(tmp_path, audio_factory)
    app = KirlianApp(library, player=FakePlayer())
    async with app.run_test(size=(120, 36)) as pilot:
        brand = app.query_one(Brand)
        await pilot.press("p")
        app.query_one("#pref-characters", Select).value = "ascii"
        await pilot.pause()
        assert brand.render().plain == "\n".join(ASCII_MARK)
        assert brand.render().plain.isascii()
        app.query_one("#pref-logo", Select).value = "text"
        await pilot.pause()
        assert brand.render().plain == "*  kirlian"
        await pilot.press("escape")
        assert brand.render().plain == drawn_wordmark()
        await pilot.press("p")
        app.query_one("#pref-logo", Select).value = "text"
        await pilot.pause()
        await pilot.click("#appearance-keep")
        assert Appearance.load(library).logo == "text"
        assert brand.render().plain == "✳  kirlian"

    restored = KirlianApp(library, player=FakePlayer())
    async with restored.run_test(size=(120, 36)) as pilot:
        await pilot.pause()
        assert restored.query_one(Brand).render().plain == "✳  kirlian"
