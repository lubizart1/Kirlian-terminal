# SPDX-License-Identifier: GPL-3.0-or-later
import asyncio
import sqlite3
import threading
from dataclasses import replace

import pytest
from test_app import FakePlayer, populated, wait_for
from textual.widgets import Button, DataTable, Select, Static

from kirlian_terminal.app import KirlianApp, PlayerUpdate
from kirlian_terminal.appearance import Appearance
from kirlian_terminal.brand import Brand
from kirlian_terminal.library import Library
from kirlian_terminal.playback import PlaybackState
from kirlian_terminal.visuals import Animation


@pytest.fixture(autouse=True)
def desktop_terminal(monkeypatch):
    monkeypatch.setenv("TERM", "xterm-256color")


def test_preferences_validate_old_and_malformed_settings(tmp_path):
    library = Library(tmp_path / "library.db")
    library.set_setting("animations_enabled", "false")
    assert Appearance.load(library).motion == "off"
    library.set_setting("appearance", '{"palette":"neon","motion":"still","surprise":true}')
    assert Appearance.load(library) == Appearance(motion="still")
    library.set_setting("appearance", "[1, 2]")
    assert Appearance.load(library).motion == "off"
    Appearance(palette="sage", characters="ascii").save(library)
    assert Appearance.load(library).palette == "sage"


async def test_live_preferences_preserve_track_seed_queue_and_cancel(tmp_path, audio_factory):
    library, paths = populated(tmp_path, audio_factory)
    player = FakePlayer()
    app = KirlianApp(library, player=player)
    async with app.run_test(size=(120, 36)) as pilot:
        await wait_for(pilot, lambda: app.ready)  # Library loaded, player up.
        await pilot.press("enter", "j")
        selection = app.selected()
        player.state = PlaybackState(paused=False, idle=False, started_serial=1, path=paths[0])
        app.on_player_update(PlayerUpdate(player.state))
        animation = app.query_one(Animation)
        seed = animation.clock.variation
        await pilot.press("p")
        assert app.personalizing
        app.query_one("#pref-palette", Select).value = "sage"
        app.query_one("#pref-motion", Select).value = "still"
        await pilot.pause()
        assert app.theme == "kirlian-sage"
        assert animation.timer is None
        phase = animation.clock.time(1000000000)
        app.query_one("#pref-characters", Select).value = "ascii"
        await pilot.pause()
        assert animation.clock.time(1000000001) == phase
        assert animation.clock.variation == seed
        assert all(ord(c) < 128 for c in animation.render().plain)
        assert not player.calls
        assert library.setting("appearance") is None
        # A dropdown consumes its own Escape before the page cancels.
        await pilot.press("enter", "escape")
        assert app.personalizing
        await pilot.press("escape")
        assert not app.personalizing
        assert app.appearance == Appearance()
        assert app.selected() == selection
        assert animation.clock.variation == seed
        assert isinstance(app.focused, DataTable)
        await pilot.press("p")
        app.query_one("#pref-palette", Select).value = "amber"
        app.query_one("#pref-motion", Select).value = "off"
        await pilot.pause()
        await pilot.click("#appearance-keep")
        await wait_for(pilot, lambda: not app.personalizing)  # Saved in the background.
        assert Appearance.load(library) == replace(Appearance(), palette="amber", motion="off")
        assert animation.render().plain == ""
        assert not player.calls
        await pilot.resize_terminal(80, 24)
        await pilot.press("p")
        assert app.query_one("#appearance-keep").region.bottom <= app.size.height
        assert not app.screen.show_horizontal_scrollbar


async def test_save_reads_visible_choices_before_change_messages_arrive(tmp_path, audio_factory):
    library, _ = populated(tmp_path, audio_factory)
    app = KirlianApp(library, player=FakePlayer())
    async with app.run_test(size=(120, 36)) as pilot:
        await wait_for(pilot, lambda: app.ready)  # Library loaded, player up.
        await pilot.press("p")
        # Select posts its change message asynchronously. Saving must use the
        # visible value, even if that message has not reached the app yet.
        app.query_one("#pref-palette", Select).value = "sage"
        app.query_one("#pref-motion", Select).value = "still"
        app.finish_personalizing(True)
        await wait_for(pilot, lambda: not app.personalizing)  # Saved in the background.
        assert Appearance.load(library) == Appearance(palette="sage", motion="still")


@pytest.mark.parametrize("size", [(120, 36), (80, 24)])
async def test_keyboard_preview_save_reopen_and_reset_cancel(
    tmp_path, audio_factory, monkeypatch, size
):
    monkeypatch.delenv("NO_COLOR", raising=False)
    library, _ = populated(tmp_path, audio_factory)
    player = FakePlayer()
    app = KirlianApp(library, player=player, artwork="off")
    expected = Appearance(palette="sage", motion="still", characters="ascii")
    async with app.run_test(size=size) as pilot:
        await wait_for(pilot, lambda: app.ready)  # Library loaded, player up.
        await pilot.press("p", "enter", "down", "enter")
        await pilot.pause()
        assert app.query_one("#appearance-keep").styles.background.hex == "#33493A"
        assert "Sage" in app.query_one("#appearance-preview", Static).render().plain
        assert "Unsaved preview" in str(app.query_one("#appearance-feedback", Static).content)
        assert "album's colors" in str(app.query_one("#appearance-explanation", Static).content)
        fields = app.query_one("#appearance-fields")
        palette = app.query_one("#pref-palette")
        assert palette.region.y >= fields.region.y
        assert palette.region.bottom <= fields.region.bottom
        for _ in range(2):
            await pilot.press("tab", "enter", "down", "enter")
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: not app.personalizing)
        assert Appearance.load(library) == expected
        assert "saved for next time" in str(app.query_one("#status", Static).content)
        assert not player.calls

    restored = KirlianApp(Library(library.database), player=FakePlayer(), artwork="off")
    async with restored.run_test(size=size) as pilot:
        await pilot.pause()
        assert restored.appearance == expected
        assert restored.query_one(Brand).render().plain == "*  kirlian"
        assert restored.query_one(Animation).timer is None
        await pilot.press("p")
        await pilot.click("#appearance-reset")
        await pilot.pause()
        assert restored.appearance == Appearance()
        assert Appearance.load(library) == expected
        assert restored.query_one("#appearance-keep").region.bottom <= size[1]
        assert not restored.screen.show_horizontal_scrollbar
        await pilot.press("escape")
        assert restored.appearance == expected
        assert Appearance.load(library) == expected


async def test_slow_failed_save_preserves_preview_and_allows_retry(
    tmp_path, audio_factory, monkeypatch
):
    library, paths = populated(tmp_path, audio_factory)
    player = FakePlayer()
    app = KirlianApp(library, player=player, artwork="off")
    started, release = threading.Event(), threading.Event()
    original = library.set_setting

    def failed_save(key, value):
        if key == "appearance":
            started.set()
            release.wait(5)
            raise sqlite3.OperationalError("database is locked")
        return original(key, value)

    monkeypatch.setattr(library, "set_setting", failed_save)
    async with app.run_test(size=(120, 36)) as pilot:
        await wait_for(pilot, lambda: app.ready)  # Library loaded, player up.
        await pilot.press("p", "enter", "down", "enter", "ctrl+s")
        try:
            async with asyncio.timeout(2):
                while not started.is_set():
                    await asyncio.sleep(0.01)
            assert app.appearance_saving
            assert app.query_one("#appearance-keep", Button).disabled
            assert "Saving" in str(app.query_one("#appearance-feedback", Static).content)
            # Player events and the UI remain responsive while SQLite waits.
            state = PlaybackState(path=paths[0], position=10, paused=True, idle=False)
            app.post_message(PlayerUpdate(state))
            await pilot.press("escape")
            await pilot.pause()
            assert app.display_state.position == 10
            assert app.personalizing
        finally:
            release.set()
        async with asyncio.timeout(2):
            while app.appearance_saving:
                await asyncio.sleep(0.01)
        assert "Could not save" in str(app.query_one("#appearance-feedback", Static).content)
        assert app.appearance.palette == "sage"
        assert library.setting("appearance") is None
        assert not app.query_one("#appearance-keep", Button).disabled
        monkeypatch.setattr(library, "set_setting", original)
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: not app.personalizing)  # The retry saves in the background.
        assert Appearance.load(library).palette == "sage"
        assert not player.calls


async def test_color_disabled_and_paused_motion_are_explained(tmp_path, audio_factory, monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    library, _ = populated(tmp_path, audio_factory)
    app = KirlianApp(library, player=FakePlayer(), artwork="off")
    async with app.run_test(size=(80, 24)) as pilot:
        await wait_for(pilot, lambda: app.ready)  # Library loaded, player up.
        await pilot.press("p")
        context = str(app.query_one("#appearance-context", Static).content)
        assert "NO_COLOR" in context
        assert "stays still" in context


async def test_arrows_move_between_settings_and_step_through_choices(tmp_path, audio_factory):
    library, _ = populated(tmp_path, audio_factory)
    app = KirlianApp(library, player=FakePlayer())
    async with app.run_test(size=(120, 36)) as pilot:
        await wait_for(pilot, lambda: app.ready)  # Library loaded, player up.
        await pilot.press("p")
        await pilot.pause()

        def value(name):
            return app.query_one(f"#pref-{name}", Select).value

        palette, motion = value("palette"), value("motion")
        assert app.focused.id == "pref-palette"
        await pilot.press("down")
        assert app.focused.id == "pref-motion" and value("palette") == palette
        await pilot.press("right")
        await pilot.pause()
        assert value("motion") != motion and app.focused.id == "pref-motion"
        await pilot.press("left")
        await pilot.pause()
        assert value("motion") == motion
        await pilot.press("up", "right")
        await pilot.pause()
        assert app.focused.id == "pref-palette" and value("palette") != palette
        await pilot.press("enter")  # The full list still opens.
        await pilot.pause()
        assert app.query_one("#pref-palette", Select).expanded


async def test_theme_files_appear_in_p_recolor_everything_and_reload_when_edited(
    tmp_path, audio_factory
):
    from kirlian_terminal.appearance import COLORS

    library, _ = populated(tmp_path, audio_factory)
    themes = library.database.parent / "themes"
    themes.mkdir()
    neon = themes / "neon.toml"
    neon.write_text('name = "Neon"\naccent = "#00ff88"\ntext = "#fafafa"\n')
    (themes / "broken.toml").write_text('accent = "green"\n')
    app = KirlianApp(library, player=FakePlayer())
    async with app.run_test(size=(120, 40)) as pilot:
        await wait_for(pilot, lambda: app.ready)  # Library loaded, player up.
        await pilot.press("p")
        await pilot.pause()
        palette = app.query_one("#pref-palette", Select)
        assert ("Neon", "custom-neon") in [(str(p), v) for p, v in palette._options]
        assert "broken.toml" in str(app.query_one("#appearance-context").content)
        palette.value = "custom-neon"
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: not app.personalizing)  # p is ignored while saving.
        assert COLORS.accent == "#00ff88" and COLORS.text == "#fafafa"
        assert app.get_css_variables()["k-accent"] == "#00ff88"
        assert COLORS.selection == "#493247"  # Lines left out keep the default.

        neon.write_text('name = "Neon"\naccent = "#ff0088"\n')  # Edited while open.
        await pilot.press("p")
        await pilot.pause()
        assert COLORS.accent == "#ff0088" and app.get_css_variables()["k-accent"] == "#ff0088"
        await pilot.press("escape")

        neon.unlink()  # The theme in use is gone: the default palette takes over.
        await pilot.press("p")
        await pilot.pause()
        assert app.appearance.palette == "aubergine" and COLORS.accent == "#c69bb9"
