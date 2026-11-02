# SPDX-License-Identifier: GPL-3.0-or-later
import json
import threading
from dataclasses import replace
from pathlib import Path

from textual.widgets import DataTable, Input

from kirlian_terminal.app import KirlianApp, PlayerUpdate
from kirlian_terminal.dialogs import FolderDialog
from kirlian_terminal.facts import FactsConfig
from kirlian_terminal.library import Library, albums_from
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

    async def resume(self, paths, index, position):
        self.calls.append(("resume", list(paths), index, position))


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


async def test_the_system_picker_opens_the_chosen_folder_or_leaves_typing(
    tmp_path, audio_factory, monkeypatch
):
    from textual.widgets import Button, Static

    from kirlian_terminal import picker

    music = tmp_path / "Picked music"
    audio_factory(music / "1.wav", title="Song", album="Album", artist="Artist")
    answers = [None, music]  # Cancelled first, then a folder.

    async def choose(prompt):
        answer = answers.pop(0)
        if answer == "broken":
            raise picker.PickerError
        return answer and str(answer)

    def ready(app):
        return isinstance(app.screen, FolderDialog) and app.screen.query("#folder-path")

    monkeypatch.setattr(picker, "command", lambda prompt: ["picker"])
    monkeypatch.setattr(picker, "choose", choose)
    library = Library(tmp_path / "library.db")
    app = KirlianApp(library, player=FakePlayer())
    async with app.run_test(size=(80, 24)) as pilot:
        await wait_for(pilot, lambda: ready(app))
        browse = app.screen.query_one("#folder-browse", Button)
        browse.press()
        await pilot.pause()
        assert isinstance(app.screen, FolderDialog)  # Cancelling the picker changes nothing.
        answers.append("broken")
        browse.press()
        await wait_for(pilot, lambda: not isinstance(app.screen, FolderDialog))
        # The scan records the folder in the background.
        await wait_for(pilot, lambda: library.setting("music_folder") == str(music.resolve()))

        await wait_for(pilot, lambda: not app.scanning)
        app.action_folder()  # Without a desktop picker, typing is the way, and failures say so.
        await wait_for(pilot, lambda: ready(app))
        browse = app.screen.query_one("#folder-browse", Button)
        browse.press()
        await pilot.pause()
        error = app.screen.query_one("#folder-error", Static).content
        assert "Type the path" in str(error)
    monkeypatch.setattr(picker, "command", lambda prompt: None)
    app = KirlianApp(Library(tmp_path / "other.db"), player=FakePlayer())
    async with app.run_test(size=(80, 24)) as pilot:
        await wait_for(pilot, lambda: ready(app))
        assert not app.screen.query("#folder-browse")


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
    FactsConfig(["exa"]).save(library)
    credentials = Credentials()
    credentials.save(PROVIDERS["exa"], "key", remember=True)
    release_first = threading.Event()
    asked = []

    def fetch(provider, track, key, model, about="song"):
        if about == "album":
            return []  # Album notes have their own test.
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
        await wait_for(pilot, lambda: app.fact_cache.saved("artist\x1falbum\x1fsong 2", "en", []))
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


async def test_facts_settings_adds_a_key_orders_providers_and_typing_is_not_a_shortcut(
    tmp_path, audio_factory, monkeypatch
):
    import keyring

    from kirlian_terminal.dialogs import FactsSettings, KeyDialog

    for name in ("EXA_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    library, _ = populated(tmp_path, audio_factory)
    player = FakePlayer()
    app = KirlianApp(library, player=player)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.press("i")
        await wait_for(pilot, lambda: isinstance(app.screen, FactsSettings))
        await pilot.press("j", "enter")  # Rows: Exa, OpenAI, …
        await wait_for(pilot, lambda: isinstance(app.screen, KeyDialog))
        await pilot.press("enter")
        assert "Paste a key" in str(app.screen.query_one("#facts-error").content)
        await pilot.press("q", "space", "n", "o", "J", "t", "enter")
        await wait_for(pilot, lambda: app.facts_config.order == ["openai"] and app.facts_on)
        assert not player.calls
        assert keyring.get_password("kirlian-terminal", "openai") == "q noJt"
        assert keyring.get_password("kirlian-terminal", "exa") is None

        # Rows follow the order: OpenAI (primary), then unused Exa, Anthropic, …
        screen = app.screen
        assert screen.row_ids[0] == "openai" and screen.selected_id == "openai"
        await pilot.press("j", "j", "space")
        await wait_for(pilot, lambda: app.facts_config.order == ["openai", "anthropic"])
        await pilot.pause()
        assert screen.selected_id == "anthropic" and screen.row_ids[1] == "anthropic"
        assert "Fallback: asked only if OpenAI fails" in str(
            screen.query_one("#facts-detail").content
        )
        await pilot.press("K")  # The selection moves with its row.
        await wait_for(pilot, lambda: app.facts_config.order == ["anthropic", "openai"])
        await pilot.pause()
        assert screen.row_ids[:2] == ["anthropic", "openai"] and screen.selected_id == "anthropic"
        await pilot.press("j", "1")
        await wait_for(pilot, lambda: app.facts_config.order == ["openai", "anthropic"])
        await pilot.pause()
        await pilot.press("j", "m")  # Anthropic: pick a listed model.
        await wait_for(pilot, lambda: app.screen.query("#model-choices"))
        await pilot.press("down", "enter")
        await wait_for(pilot, lambda: app.facts_config.models == {"anthropic": "claude-haiku-5-5"})
        await pilot.press("m")
        await wait_for(pilot, lambda: app.screen.query("#model-choices"))
        await pilot.press("up", "enter")  # Back to the default removes the override.
        await wait_for(pilot, lambda: app.facts_config.models == {})
        await pilot.press("t")
        await wait_for(pilot, lambda: not app.facts_on)
        await pilot.press("escape")
        await pilot.pause()
        stored = FactsConfig.load(library)
        assert stored.order == ["openai", "anthropic"]
        assert library.setting("facts") == "off"
        assert keyring.get_password("kirlian-terminal", "openai") == "q noJt"


async def test_facts_fall_back_on_errors_and_a_fallback_answer_is_not_paid_for_twice(
    tmp_path, audio_factory, monkeypatch
):
    from kirlian_terminal.app import PlayerUpdate
    from kirlian_terminal.facts import PROVIDERS, Credentials, Fact, FactsError

    for name in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(KirlianApp, "FACT_DELAY", 0)
    library, paths = populated(tmp_path, audio_factory)
    library.set_setting("facts", "on")
    FactsConfig(["anthropic", "openai"], {"anthropic": "claude-test"}).save(library)
    credentials = Credentials()
    for provider in ("anthropic", "openai"):
        credentials.save(PROVIDERS[provider], "key", remember=True)
    calls = []
    failing = {"anthropic"}

    def fetch(provider, track, key, model, about="song"):
        if about == "album":
            return []  # Album notes have their own test.
        calls.append((provider.id, model))
        if provider.id in failing:
            raise FactsError(f"{provider.name} rate limit or credits reached.")
        return [
            Fact(
                f"From {provider.name}",
                "Body.",
                "Src",
                "https://e.org",
                kind="reading",
                provider=provider.name,
            )
        ]

    app = KirlianApp(library, player=FakePlayer(), credentials=credentials, fetch_facts=fetch)

    def card():
        shown = app.query_one("#fact-card").display
        return shown and app.query_one("#fact-text").content.plain

    async with app.run_test(size=(140, 50)) as pilot:
        await pilot.press("enter")
        state = PlaybackState(path=paths[0], paused=False, idle=False, started_serial=1)
        app.on_player_update(PlayerUpdate(state))
        await wait_for(pilot, lambda: card() and "From OpenAI" in card())
        assert calls == [("anthropic", "claude-test"), ("openai", "gpt-5.4-mini")]
        assert "rate limit" in app.query_one("#status").content.plain
        source_line = app.query_one("#fact-source").content.plain
        assert "A reading, drawing on Src" in source_line and "via OpenAI" in source_line

        # The primary recovers, but this song is already answered: nothing more is billed.
        failing.clear()
        app.facts_settings_closed()
        await pilot.pause(0.2)
        assert len(calls) == 2 and "From OpenAI" in card()


async def test_a_dropped_connection_is_retried_next_play_and_unused_keys_are_suggested(
    tmp_path, audio_factory, monkeypatch
):
    from kirlian_terminal.app import PlayerUpdate
    from kirlian_terminal.facts import PROVIDERS, Credentials, Fact, FactsError

    for name in ("PERPLEXITY_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(KirlianApp, "FACT_DELAY", 0)
    library, paths = populated(tmp_path, audio_factory)
    library.set_setting("facts", "on")
    FactsConfig(["perplexity"]).save(library)
    credentials = Credentials()
    for provider in ("perplexity", "anthropic"):
        credentials.save(PROVIDERS[provider], "key", remember=True)
    calls = []

    def fetch(provider, track, key, model, about="song"):
        if about == "album":
            return []  # Album notes have their own test.
        calls.append(provider.id)
        if len(calls) == 1:
            raise FactsError("Could not reach Perplexity (connection dropped).", transient=True)
        return [Fact("Back", "Body.", "Src", "https://e.org", provider=provider.name)]

    app = KirlianApp(library, player=FakePlayer(), credentials=credentials, fetch_facts=fetch)

    def play(path, serial):
        state = PlaybackState(path=path, paused=False, idle=False, started_serial=serial)
        app.on_player_update(PlayerUpdate(state))

    async with app.run_test(size=(140, 50)) as pilot:
        await pilot.press("enter")
        play(paths[0], 1)
        await wait_for(
            pilot, lambda: "Anthropic has a key" in str(app.query_one("#status").content)
        )
        play(paths[1], 2)
        await pilot.pause(0.1)
        play(paths[0], 3)  # The same song again: a dropped connection is retried.
        await wait_for(pilot, lambda: calls.count("perplexity") == 3)
        assert "anthropic" not in calls  # Unused providers are suggested, never billed.


async def test_question_mark_toggles_one_key_guide(tmp_path, audio_factory):
    library, _ = populated(tmp_path, audio_factory)

    def guides():
        return len(app._notifications)  # Textual's list of notifications on screen.

    app = KirlianApp(library, player=FakePlayer())
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.press("question_mark")
        await wait_for(pilot, lambda: guides() == 1)
        await pilot.press("question_mark")
        await wait_for(pilot, lambda: guides() == 0)
        await pilot.press("question_mark", "question_mark", "question_mark")
        await wait_for(pilot, lambda: guides() == 1)


async def test_a_slow_load_of_a_playlist_left_behind_never_replaces_the_open_one(
    tmp_path, audio_factory
):
    """Delete, move, and play act on the shown rows, so they must be the open playlist's."""
    import time

    library, paths = populated(tmp_path, audio_factory)
    app = KirlianApp(library, player=FakePlayer())
    async with app.run_test() as pilot:
        await pilot.pause()
        first, second = app.playlists.create("First"), app.playlists.create("Second")
        app.playlists.add(first, [str(paths[0])])
        app.playlists.add(second, [str(paths[1])])
        entries = app.playlists.entries

        def slow_first(playlist_id):
            if playlist_id == first:
                time.sleep(0.3)
            return entries(playlist_id)

        app.playlists.entries = slow_first
        slow = app.open_playlist(str(first))
        await pilot.pause(0.05)
        app.open_playlist(str(second))
        await slow.wait()
        await pilot.pause()
        assert app.view_value == str(second)
        assert [entry.path for entry in app.playlist_entries] == [str(paths[1])]


async def test_an_upgraded_library_is_rescanned_once_so_song_notes_keep_working(
    tmp_path, audio_factory
):
    import sqlite3

    library, _ = populated(tmp_path, audio_factory)
    with sqlite3.connect(library.database) as db:  # The library as an older version left it.
        db.execute("ALTER TABLE tracks DROP COLUMN tagged")
    upgraded = Library(library.database)
    assert not any(track.tagged for track in upgraded.tracks())
    app = KirlianApp(upgraded, player=FakePlayer())
    async with app.run_test() as pilot:
        await wait_for(pilot, lambda: app.tracks and all(t.tagged for t in app.tracks))
    assert upgraded.setting("rescan") is None


async def test_relaunching_brings_back_the_queue_paused_where_listening_stopped(
    tmp_path, audio_factory
):
    library, paths = populated(tmp_path, audio_factory)
    queue = [{"filename": path} for path in paths]
    app = KirlianApp(library, player=FakePlayer())
    async with app.run_test() as pilot:
        await wait_for(pilot, lambda: app.ready)
        for position in (1.0, 2.0, 7.4, 8.0):  # Saved every few seconds, not every update.
            state = PlaybackState(
                path=paths[1], index=1, idle=False, paused=False, position=position, playlist=queue
            )
            app.on_player_update(PlayerUpdate(state))
        assert json.loads(library.setting("resume"))["position"] == 7.4
        app.player.state = state
        await pilot.press("q")  # Quitting saves the exact place.

    Path(paths[0]).unlink()  # A song removed since: the rest of the queue comes back.
    player = FakePlayer()
    app = KirlianApp(library, player=player)
    async with app.run_test() as pilot:
        await wait_for(pilot, lambda: any(call[0] == "resume" for call in player.calls))
    assert ("resume", [paths[1]], 0, 8.0) in player.calls
    assert not any(call[0] in {"play", "pause", "jump"} for call in player.calls)


async def test_a_clipped_title_scrolls_while_highlighted_and_returns_whole_after(
    tmp_path, audio_factory, monkeypatch
):
    from kirlian_terminal import app as app_module
    from kirlian_terminal import marquee

    monkeypatch.setattr(app_module, "MARQUEE_STEP", 0.01)
    monkeypatch.setattr(marquee, "HOLD", 2)
    long_title = "A Very Long Album Title That Cannot Possibly Fit In Eighty Columns At All"
    library, _ = populated(tmp_path, audio_factory)
    root = tmp_path / "Music"
    audio_factory(root / "Long" / "1.wav", title="Song", album=long_title, artist="Artist")
    library.scan(root, lambda _: None, threading.Event())
    app = KirlianApp(library, player=FakePlayer())
    async with app.run_test(size=(80, 24)) as pilot:
        table = app.query_one(DataTable)
        await wait_for(pilot, lambda: table.row_count == 2)
        row = next(i for i, r in enumerate(app.rows) if r.title == long_title)
        table.move_cursor(row=row)

        def shown():
            return table.get_cell_at((row, 0)).plain

        await wait_for(pilot, lambda: not shown().startswith("A Very"))
        assert shown() in long_title + marquee.GAP + long_title
        table.move_cursor(row=1 - row)
        await wait_for(pilot, lambda: shown() == long_title)

        app.appearance = replace(app.appearance, motion="still")
        table.move_cursor(row=row)
        await pilot.pause(0.2)
        assert shown() == long_title


async def test_arrows_choose_among_search_results_while_typing(tmp_path, audio_factory):
    library, paths = populated(tmp_path, audio_factory)
    player = FakePlayer()
    app = KirlianApp(library, player=player)
    async with app.run_test(size=(120, 32)) as pilot:
        await pilot.pause()
        await pilot.press("slash", *"song")
        await pilot.pause()
        assert [row.kind for row in app.rows] == ["track", "track"]
        await pilot.press("down", "down", "up", "down")  # Stops at the last result.
        assert app.focused.id == "search"  # Typing can continue.
        chosen = app.rows[1].value
        await pilot.press("enter")
        await pilot.pause()
        assert player.calls == [("play", paths, paths.index(chosen))]


async def test_a_full_disk_never_closes_the_player(tmp_path, audio_factory, monkeypatch):
    import sqlite3

    library, _ = populated(tmp_path, audio_factory)

    def full_disk(*args, **kwargs):
        raise sqlite3.OperationalError("unable to open database file")

    app = KirlianApp(library, player=FakePlayer())
    async with app.run_test(size=(120, 36)) as pilot:
        await pilot.pause()

        def status():
            return app.query_one("#status").content.plain

        saving = library.set_setting
        monkeypatch.setattr(library, "set_setting", full_disk)
        monkeypatch.setattr(app.playlists, "create", full_disk)
        await pilot.press("E", "j", "right", "escape")  # Change a preset: saved in a worker.
        app.create_playlist("Mix")
        await pilot.pause(0.6)
        assert app.is_running and "Is the disk full?" in status()
        await pilot.press("c")  # The display switches, but the listener learns it won't last.
        assert "Is the disk full?" in status()
        await pilot.press("s")  # A pattern that could not be saved is not counted as saved.
        assert "Is the disk full?" in status() and not app.saved_animations

        monkeypatch.setattr(library, "set_setting", saving)  # Space again: s now saves.
        await pilot.press("s")
        assert len(app.saved_animations) == 1 and library.setting("saved_animations")


async def test_playbar_buttons_and_clicking_the_progress_line(tmp_path, audio_factory):
    library, paths = populated(tmp_path, audio_factory)
    player = FakePlayer()
    app = KirlianApp(library, player=player, characters="dots")
    async with app.run_test(size=(120, 36)) as pilot:
        await pilot.pause()
        player.state = PlaybackState(
            path=paths[0], idle=False, paused=False, duration=200, position=10
        )
        app.on_player_update(PlayerUpdate(player.state))
        await pilot.pause()
        progress = app.query_one("#progress")
        await pilot.click("#progress", offset=(progress.size.width // 2, 0))
        await pilot.pause()
        seek = player.calls[-1]
        assert seek[0] == "seek" and seek[2] == "absolute-percent+exact"
        assert 49 <= seek[1] <= 51  # The middle of the line is the middle of the song.

        transport = app.query_one("#transport")
        assert transport.content.plain == "|◀   ◀◀   ❚❚   ▶▶   ▶|"
        expected = [
            (0, ("playlist-prev", "weak")),
            (5, ("seek", -5, "relative+exact")),
            (10, ("pause",)),
            (15, ("seek", 5, "relative+exact")),
            (20, ("playlist-next", "weak")),
        ]
        for x, call in expected:
            await pilot.click("#transport", offset=(x, 0))
            await pilot.pause()
            assert player.calls[-1] == call


async def test_b_opens_a_store_search_for_the_album_and_never_for_folder_names(
    tmp_path, audio_factory, monkeypatch
):
    import webbrowser

    opened = []
    monkeypatch.setattr(webbrowser, "open", lambda url: opened.append(url) or True)
    library, _ = populated(tmp_path, audio_factory)
    root = tmp_path / "Music"
    audio_factory(root / "Loose folder" / "1.wav", title="Untagged album")  # No album tag.
    library.scan(root, lambda _: None, threading.Event())
    app = KirlianApp(library, player=FakePlayer())
    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.pause()
        album_row = next(i for i, r in enumerate(app.rows) if r.title == "Album")
        app.query_one(DataTable).move_cursor(row=album_row)
        await pilot.pause()
        assert "Spotify" in app.query_one("#record-stores").content.plain
        await pilot.press("b", "down", "enter")  # The second store: Apple Music.
        await wait_for(pilot, lambda: opened)
        assert opened == ["https://music.apple.com/search?term=Artist+Album"]
        links = app.query_one("#record-stores")
        await pilot.click("#record-stores", offset=(links.content.plain.index("Spotify") + 1, 0))
        await wait_for(pilot, lambda: len(opened) == 2)
        assert opened[-1] == "https://open.spotify.com/search/Artist%20Album"

        loose = next(i for i, r in enumerate(app.rows) if r.title == "Loose folder")
        app.query_one(DataTable).move_cursor(row=loose)
        await pilot.pause()
        assert not app.query_one("#record-stores").display
        await pilot.press("b")
        assert "no title and artist tags" in app.query_one("#status").content.plain
        assert len(opened) == 2


async def test_album_notes_follow_the_songs_and_each_album_is_asked_once(
    tmp_path, audio_factory, monkeypatch
):
    from kirlian_terminal.facts import PROVIDERS, Credentials, Fact

    monkeypatch.delenv("EXA_API_KEY", raising=False)
    monkeypatch.setattr(KirlianApp, "FACT_DELAY", 0)
    library, paths = populated(tmp_path, audio_factory)  # Two songs, one album.
    library.set_setting("facts", "on")
    FactsConfig(["exa"]).save(library)
    credentials = Credentials()
    credentials.save(PROVIDERS["exa"], "key", remember=True)
    asked = []

    def fetch(provider, track, key, model, about="song"):
        asked.append((about, track.title))
        headline = "The record" if about == "album" else f"On {track.title}"
        return [Fact(headline, "Body.", "Src", "https://e.org", provider=provider.name)]

    app = KirlianApp(library, player=FakePlayer(), credentials=credentials, fetch_facts=fetch)

    def play(path, serial):
        state = PlaybackState(path=path, paused=False, idle=False, started_serial=serial)
        app.on_player_update(PlayerUpdate(state))

    def card():
        return str(app.query_one("#fact-text").content)

    async with app.run_test(size=(140, 50)) as pilot:
        await pilot.press("enter")
        play(paths[0], 1)
        await wait_for(pilot, lambda: len(app.facts) == 2)
        assert [f.about for f in app.facts] == ["song", "album"]  # The song's notes first.
        assert "On Song 2" in card()
        await pilot.press("right_square_bracket")
        assert "About the album" in card() and "The record" in card()

        play(paths[1], 2)  # Another song from the same album: only the song is new.
        await wait_for(pilot, lambda: len(app.facts) == 2 and "Song 10" in app.facts[0].headline)
        assert asked == [("song", "Song 2"), ("album", "Song 2"), ("song", "Song 10")]

        app.facts_config.albums = False  # Switched off: no album notes, none requested.
        with library.connect() as db:  # Forget the saved answers, so the song is asked again.
            db.execute("DELETE FROM facts")
        app.facts_settings_closed()  # As when the setting is changed with i.
        play(paths[0], 3)
        await wait_for(pilot, lambda: len(asked) == 4)
        await pilot.pause(0.2)
        assert asked[-1] == ("song", "Song 2") and [f.about for f in app.facts] == ["song"]


def test_a_queue_holding_one_song_twice_resumes_at_the_right_copy(tmp_path, audio_factory):
    from kirlian_terminal.resume import Place

    a, b, c = (str(audio_factory(tmp_path / f"{n}.wav")) for n in "abc")
    library = Library(tmp_path / "library.db")
    Place((a, b, a, c), 2, 30.0).save(library)  # On the second copy of a.
    assert Place.load(library) == Place((a, b, a, c), 2, 30.0)
    Path(b).unlink()  # An earlier song gone: still the second copy, now one place up.
    assert Place.load(library) == Place((a, a, c), 1, 30.0)


def test_stores_need_album_and_artist_tags_not_every_title(tmp_path, audio_factory):
    from kirlian_terminal.stores import searchable

    root = tmp_path / "Music"
    audio_factory(root / "Tagged" / "1.wav", title="One", album="Record", artist="Band")
    audio_factory(root / "Tagged" / "2.wav", album="Record", artist="Band")  # No title tag.
    audio_factory(root / "No artist" / "1.wav", title="One", album="Anonymous")
    library = Library(tmp_path / "library.db")
    library.scan(root, lambda _: None, threading.Event())
    albums = {album.title: album for album in albums_from(library.tracks())}
    assert searchable(albums["Record"])
    assert not searchable(albums["Anonymous"])  # Would search for "Unknown artist".
