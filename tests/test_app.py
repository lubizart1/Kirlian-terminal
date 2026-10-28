# SPDX-License-Identifier: GPL-3.0-or-later
import threading
from pathlib import Path

from textual.widgets import DataTable, Input

from kirlian_terminal.app import FolderDialog, KirlianApp
from kirlian_terminal.library import Library
from kirlian_terminal.playback import PlaybackState


class FakePlayer:
    def __init__(self):
        self.state = PlaybackState()
        self.calls = []
        self.on_change = lambda state: None

    async def start(self):
        pass

    async def close(self):
        self.calls.append(("close",))

    async def play(self, paths, index=0):
        self.calls.append(("play", paths, index))

    async def append(self, paths):
        self.calls.append(("append", paths))

    async def toggle_pause(self):
        self.calls.append(("pause",))

    async def command(self, *args):
        self.calls.append(args)

    async def control(self, *args):
        self.calls.append(args)

    async def jump(self, index):
        self.calls.append(("jump", index))


def populated(tmp_path, audio_factory):
    root = tmp_path / "Music"
    paths = [
        audio_factory(
            root / f"{n}.wav", title=f"Song {n}", album="Album", artist="Artist", track=str(n)
        )
        for n in (2, 10)
    ]
    library = Library(tmp_path / "library.db")
    library.scan(root, lambda _: None, threading.Event())
    return library, [str(p) for p in paths]


async def test_search_typing_does_not_trigger_controls_and_escape_restores(tmp_path, audio_factory):
    library, paths = populated(tmp_path, audio_factory)
    player = FakePlayer()
    app = KirlianApp(library, player=player)
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        assert len(app.rows) == 1
        assert not app.query_one("#context").display
        await pilot.press("enter", "j")
        assert app.query_one(DataTable).cursor_row == 1
        await pilot.press("slash")
        await pilot.press("a", "space", "q", "n", "H", "L", "minus", "equals_sign", "slash")
        assert app.query_one("#search", Input).value == "a qnHL-=/"
        await pilot.press("left", "right")
        assert app.searching
        assert not player.calls
        await pilot.press("escape")
        assert app.view == "album"
        assert app.query_one(DataTable).cursor_row == 1
        await pilot.press("enter")
        await pilot.pause()
        assert player.calls == [("play", paths, 1)]


async def test_arrow_navigation(tmp_path, audio_factory):
    library, _ = populated(tmp_path, audio_factory)
    app = KirlianApp(library, player=FakePlayer())
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        await pilot.press("right")
        assert app.view == "album"
        await pilot.press("down")
        assert app.query_one(DataTable).cursor_row == 1
        await pilot.press("left")
        assert app.view == "albums"


async def test_resize_keeps_rows_and_selection_without_rebuilding(
    tmp_path, audio_factory, monkeypatch
):
    library, _ = populated(tmp_path, audio_factory)
    app = KirlianApp(library, player=FakePlayer())
    async with app.run_test(size=(120, 36)) as pilot:
        await pilot.pause()
        await pilot.press("enter", "down")
        selection = app.selected()
        table = app.query_one(DataTable)
        keys = list(table.rows)

        def unexpected_clear(*args, **kwargs):
            raise AssertionError("Resizing must not rebuild the music library")

        monkeypatch.setattr(table, "clear", unexpected_clear)
        await pilot.resize_terminal(80, 24)
        await pilot.pause()
        assert not table.show_horizontal_scrollbar
        assert table.virtual_size.width <= table.size.width
        await pilot.resize_terminal(160, 48)
        await pilot.pause()
        assert list(table.rows) == keys
        assert app.selected() == selection


async def test_position_updates_do_not_relayout_labels_or_duplicate_motion_frames(
    tmp_path, audio_factory, monkeypatch
):
    from dataclasses import replace

    from kirlian_terminal.app import PlayerUpdate
    from kirlian_terminal.visuals import Animation

    library, paths = populated(tmp_path, audio_factory)
    app = KirlianApp(library, player=FakePlayer())
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        state = PlaybackState(
            path=paths[0], paused=False, idle=False, duration=200, started_serial=1
        )
        app.on_player_update(PlayerUpdate(state))
        await pilot.pause()
        animation = app.query_one(Animation)
        draws = []
        draw = animation.draw
        monkeypatch.setattr(animation, "draw", lambda: draws.append(True))
        refreshes = []
        for selector in (
            "#play-state",
            "#playing-label",
            "#playing-time",
            "#volume",
            "#shortcuts",
            "#search-hint",
            "#animation",
        ):
            widget = app.query_one(selector)
            refresh = widget.refresh

            def record(*args, _refresh=refresh, **kwargs):
                refreshes.append(kwargs)
                return _refresh(*args, **kwargs)

            monkeypatch.setattr(widget, "refresh", record)
        for position in range(1, 21):
            app.on_player_update(PlayerUpdate(replace(state, position=position)))
        assert not draws
        draw()
        assert refreshes
        assert not any(call.get("layout") for call in refreshes)
        assert app.query_one("#playing-time").content.plain == "0:20 / 3:20"


async def test_song_search_starts_album_queue_and_browsing_does_not_replace_it(
    tmp_path, audio_factory
):
    library, paths = populated(tmp_path, audio_factory)
    player = FakePlayer()
    app = KirlianApp(library, player=player)
    async with app.run_test(size=(120, 32)) as pilot:
        await pilot.pause()
        assert app.query_one("#context").display
        await pilot.resize_terminal(80, 24)
        await pilot.pause()
        assert not app.query_one("#context").display
        assert app.query_one(DataTable).size.height >= 8
        assert not app.query_one(DataTable).show_horizontal_scrollbar
        await pilot.resize_terminal(120, 32)
        await pilot.pause()
        assert app.query_one("#context").display
        await pilot.press("slash", "S", "o", "n", "g", "space", "1", "0", "enter")
        await pilot.pause()
        assert player.calls == [("play", paths, 1)]
        await pilot.press("escape", "h", "enter", "j", "a")
        await pilot.pause()
        assert player.calls[-1] == ("append", [paths[1]])
        assert sum(call[0] == "play" for call in player.calls) == 1


async def test_folder_typing_and_cancel(tmp_path):
    player = FakePlayer()
    app = KirlianApp(Library(tmp_path / "library.db"), player=player)
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        assert isinstance(app.screen, FolderDialog)
        await pilot.press("q", "space", "a", "n", "slash", "H")
        assert app.screen.query_one(Input).value == "q an/H"
        assert not player.calls
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, FolderDialog)
        await pilot.press("escape")
        assert not isinstance(app.screen, FolderDialog)


async def test_background_scan_arrives_in_ui(tmp_path, audio_factory):
    root = tmp_path / "Music with spaces é"
    for n in range(3):
        audio_factory(root / f"{n}.wav")
    library = Library(tmp_path / "library.db")
    app = KirlianApp(library, folder=root, player=FakePlayer())
    async with app.run_test(size=(80, 24)) as pilot:
        for _ in range(30):
            await pilot.pause(0.05)
            if len(app.tracks) == 3 and not app.scanning:
                break
        assert len(app.tracks) == 3
        assert not app.scanning
        assert len(library.tracks()) == 3


async def test_search_remains_usable_while_scan_is_running(tmp_path, audio_factory, monkeypatch):
    import kirlian_terminal.library as library_module

    root = tmp_path / "Music"
    audio_factory(root / "one.wav")
    release_reader = threading.Event()
    real_reader = library_module.read_track

    def slow_reader(path):
        release_reader.wait(timeout=10)
        return real_reader(path)

    monkeypatch.setattr(library_module, "read_track", slow_reader)
    app = KirlianApp(Library(tmp_path / "library.db"), folder=root, player=FakePlayer())
    async with app.run_test(size=(80, 24)) as pilot:
        try:
            await pilot.pause()
            assert app.scanning
            await pilot.press("slash", "a", "space", "q")
            assert app.query_one("#search", Input).value == "a q"
            assert app.scanning
        finally:
            release_reader.set()
        for _ in range(30):
            await pilot.pause(0.05)
            if not app.scanning:
                break
        assert len(app.tracks) == 1


async def test_record_caption_fits_under_cover_after_resize(tmp_path, audio_factory):
    from PIL import Image

    library, _ = populated(tmp_path, audio_factory)
    Image.new("RGB", (600, 600), "red").save(tmp_path / "Music" / "cover.png")
    app = KirlianApp(library, player=FakePlayer(), artwork="blocks")
    async with app.run_test(size=(160, 44)) as pilot:
        for _ in range(30):
            await pilot.pause(0.03)
            if app.query_one("#cover").image:
                break
        for width, height in ((160, 44), (120, 36), (120, 30)):
            await pilot.resize_terminal(width, height)
            await pilot.pause()
            assert (
                app.query_one("#record-details").region.bottom
                <= app.query_one("#context").content_region.bottom
            )


async def wait_for(pilot, condition, attempts=60):
    for _ in range(attempts):
        if condition():
            return
        await pilot.pause(0.02)
    assert condition()


async def test_playlist_keeps_saved_order_duplicates_and_missing_files(tmp_path, audio_factory):
    library, paths = populated(tmp_path, audio_factory)
    player = FakePlayer()
    app = KirlianApp(library, player=player)
    async with app.run_test(size=(120, 36)) as pilot:
        await pilot.pause()
        await pilot.press("enter", "plus", "enter")
        await pilot.pause()
        await pilot.press("E", "v", "e", "space", "q", "a", "n")
        assert app.screen.query_one(Input).value == "Eve qan"
        await pilot.press("enter")
        await wait_for(pilot, lambda: app.playlist_list and app.playlist_list[0].size == 1)
        playlist_id = app.playlist_list[0].id
        await pilot.press("j", "plus", "down", "enter")
        await wait_for(pilot, lambda: app.playlist_list[0].size == 2)
        await pilot.press("k", "plus", "down", "enter")
        await wait_for(pilot, lambda: app.playlist_list[0].size == 3)
        app.playlists.add(playlist_id, [str(tmp_path / "gone.wav")])
        assert not player.calls

        await pilot.press("slash", "E", "v", "e", "enter")
        await wait_for(pilot, lambda: app.view == "playlist" and len(app.rows) == 4)
        assert "[unavailable]" in app.rows[3].title
        await pilot.press("j", "enter")
        await pilot.pause()
        assert player.calls == [("play", [paths[0], paths[1], paths[0]], 1)]

        await pilot.press("J")
        await wait_for(
            pilot,
            lambda: [e.path for e in app.playlist_entries][:3] == [paths[0], paths[0], paths[1]],
        )
        assert app.query_one(DataTable).cursor_row == 2
        await pilot.press("j", "enter")
        await pilot.pause()
        assert len(player.calls) == 1
        await pilot.press("d")
        await wait_for(pilot, lambda: len(app.playlist_entries) == 3)

        await pilot.press("escape")
        await pilot.pause()
        assert app.view == "playlists" and app.selected().kind == "playlist"
        await pilot.press("d")
        await pilot.pause()
        await pilot.click("#confirm")
        await wait_for(pilot, lambda: not app.playlist_list)
        assert all(Path(p).exists() for p in paths)


async def test_facts_follow_the_playing_song_and_discard_late_answers(
    tmp_path, audio_factory, monkeypatch
):
    from kirlian_terminal.app import PlayerUpdate
    from kirlian_terminal.facts import PROVIDERS, Credentials, Fact

    monkeypatch.delenv("EXA_API_KEY", raising=False)
    monkeypatch.setattr(KirlianApp, "FACT_DELAY", 0)
    library, paths = populated(tmp_path, audio_factory)
    library.set_setting("facts", "on")
    credentials = Credentials()
    credentials.save(PROVIDERS["exa"], "key", remember=True)
    release_first = threading.Event()
    asked = []

    def fetch(provider, track, key):
        asked.append(track.title)
        if track.title == "Song 2":
            release_first.wait(timeout=10)
        return [
            Fact(f"About {track.title}", "Body.", "Source", "https://example.org/a", "2010"),
            Fact("Second", "More.", "Source", "https://example.org/b"),
        ]

    app = KirlianApp(library, player=FakePlayer(), credentials=credentials, fetch_facts=fetch)

    def play(path, serial):
        state = PlaybackState(path=path, paused=False, idle=False, started_serial=serial)
        app.on_player_update(PlayerUpdate(state))

    def card_text():
        card = app.query_one("#fact-card")
        return card.display and app.query_one("#fact-text").content.plain

    async with app.run_test(size=(140, 50)) as pilot:
        try:
            await pilot.press("enter")
            play(paths[0], 1)
            await wait_for(pilot, lambda: asked == ["Song 2"])
            # While Song 2's request is open, the card keeps time with its title.
            await wait_for(pilot, lambda: app.query_one("#fact-pulse").display)
            assert "Asking Exa" in card_text()
            assert not app.query_one("#fact-source").display
            play(paths[1], 2)
            await wait_for(pilot, lambda: card_text() and "About Song 10" in card_text())
            assert not app.query_one("#fact-pulse").display
            assert app.query_one("#fact-pulse").timer is None
        finally:
            release_first.set()
        await wait_for(pilot, lambda: app.fact_cache.get("artist\x1falbum\x1fsong 2"))
        await pilot.pause()
        assert "About Song 10" in card_text()
        await pilot.press("right_square_bracket")
        assert "Second" in card_text()
        play(paths[0], 3)
        await wait_for(pilot, lambda: card_text() and "About Song 2" in card_text())
        assert asked == ["Song 2", "Song 10"]
        play("", 4)
        await pilot.pause()
        assert not app.query_one("#fact-card").display


async def test_facts_setup_picks_a_provider_stores_its_key_and_typing_is_not_a_shortcut(
    tmp_path, audio_factory, monkeypatch
):
    import keyring

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    library, _ = populated(tmp_path, audio_factory)
    player = FakePlayer()
    app = KirlianApp(library, player=player)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.press("i")
        await wait_for(pilot, lambda: app.screen.query("#facts-key"))
        await pilot.press("enter", "down", "enter")
        await pilot.pause()
        assert app.screen.query_one("#facts-provider").value == "openai"
        assert "OpenAI" in str(app.screen.query_one("#facts-hint").content)
        await pilot.press("tab", "enter")
        assert "Enter an API key" in str(app.screen.query_one("#facts-error").content)
        await pilot.press("q", "space", "n", "o")
        await pilot.press("enter")
        await wait_for(pilot, lambda: app.facts_on)
        assert not player.calls
        assert keyring.get_password("kirlian-terminal", "openai") == "q no"
        assert keyring.get_password("kirlian-terminal", "exa") is None
        assert library.setting("facts_provider") == "openai"
        assert app.facts_provider.id == "openai"
