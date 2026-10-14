import threading

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
