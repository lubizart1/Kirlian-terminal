# SPDX-License-Identifier: GPL-3.0-or-later
import json

import pytest
from test_app import FakePlayer, populated
from textual.widgets import Select

from kirlian_terminal.app import KirlianApp
from kirlian_terminal.appearance import Appearance
from kirlian_terminal.brand import Brand


@pytest.fixture(autouse=True)
def desktop_terminal(monkeypatch):
    monkeypatch.setenv("TERM", "xterm-256color")


async def test_header_mark_is_one_crisp_line_at_every_size(tmp_path, audio_factory):
    library, _ = populated(tmp_path, audio_factory)
    player = FakePlayer()
    app = KirlianApp(library, player=player, artwork="native")
    async with app.run_test(size=(120, 36)) as pilot:
        brand = app.query_one(Brand)
        for size in ((120, 36), (80, 24), (160, 48)):
            await pilot.resize_terminal(*size)
            await pilot.pause()
            assert brand.render().plain == "✺  kirlian"
            assert brand.size.height == 1
            assert brand.region.right <= app.query_one("#search-hint").region.x
        assert not app.screen.show_horizontal_scrollbar
        assert not player.calls


async def test_ascii_characters_give_an_ascii_mark_and_old_logo_setting_is_ignored(
    tmp_path, audio_factory
):
    library, _ = populated(tmp_path, audio_factory)
    # Saved before the drawn wordmark was removed.
    library.set_setting("appearance", json.dumps({"palette": "sage", "logo": "auto"}))
    app = KirlianApp(library, player=FakePlayer())
    async with app.run_test(size=(120, 36)) as pilot:
        assert app.appearance == Appearance(palette="sage")
        brand = app.query_one(Brand)
        await pilot.press("p")
        app.query_one("#pref-characters", Select).value = "ascii"
        await pilot.pause()
        assert brand.render().plain == "*  kirlian"
        assert app.query_one("#fact-spark").render().plain == "*"
        await pilot.press("escape")
        assert brand.render().plain == "✺  kirlian"
        assert not app.query("#pref-logo")
