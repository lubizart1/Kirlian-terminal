"""Album browsing and playback UI. Filesystem and player work run in workers."""

from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import threading
from collections import OrderedDict
from dataclasses import dataclass, replace
from pathlib import Path

from PIL import Image as PILImage
from rich.console import Console
from rich.text import Text
from textual import events, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Input, Label, OptionList, Select, Static

from .animations import Variation
from .appearance import INK, OPTIONS, PALETTES, QUIET, Appearance, themes
from .artwork import load_artwork
from .brand import Brand
from .cover import CoverImage, RecordPane
from .graphics import NATIVE_SUPPORTED
from .library import Album, Library, ScanProgress, Track, albums_from, display_text
from .palette import extract_palette
from .playback import PlaybackError, PlaybackState, Player
from .visuals import Animation, Progress


def clock(seconds: float) -> str:
    minutes, seconds = divmod(max(0, int(seconds)), 60)
    return f"{minutes}:{seconds:02d}"


@dataclass(frozen=True)
class Row:
    kind: str
    value: str
    title: str
    detail: str = ""
    duration: str = ""


class ScanUpdate(Message):
    def __init__(self, progress: ScanProgress) -> None:
        super().__init__()
        self.progress = progress


class PlayerUpdate(Message):
    def __init__(self, state: PlaybackState) -> None:
        super().__init__()
        self.state = replace(state)


class FolderDialog(ModalScreen[str | None]):
    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def compose(self) -> ComposeResult:
        with Vertical(id="folder-dialog"):
            yield Label("Kirlian · Your music, locally")
            yield Static("Choose a folder to begin. Make it yours later with p.")
            yield Static("Your files and tags stay untouched. Indexing happens in the background.")
            yield Input(placeholder="~/Music", id="folder-path")
            yield Static("", id="folder-error")
            yield Button("Open folder", variant="primary")

    def on_mount(self) -> None:
        self.query_one(Input).focus()

    def on_input_submitted(self) -> None:
        self.submit()

    def on_button_pressed(self) -> None:
        self.submit()

    @work(exclusive=True)
    async def submit(self) -> None:
        value = self.query_one(Input).value.strip()
        folder = Path(value).expanduser()
        try:
            valid = bool(value) and await asyncio.to_thread(folder.is_dir)
        except (OSError, ValueError):
            valid = False
        if not valid:
            self.query_one("#folder-error", Static).update("Enter an existing, readable folder.")
            return
        self.dismiss(str(folder))

    def action_cancel(self) -> None:
        self.dismiss(None)


class LibraryTable(DataTable):
    def on_resize(self) -> None:
        self.app.call_after_refresh(self.app.size_columns)

    def refresh_columns(self) -> None:
        # DataTable has no public column-resize method. Direct width changes need
        # both rendered-cell invalidation and a new scroll extent, but no new rows.
        self._clear_caches()
        self._update_dimensions(())
        self.refresh(layout=True)


class KirlianApp(App):
    TITLE = "Kirlian Terminal"
    ENABLE_COMMAND_PALETTE = False
    CSS_PATH = "styles.tcss"
    BINDINGS = [
        Binding("j", "down", "Down"),
        Binding("k", "up", "Up"),
        Binding("h", "back", "Back"),
        Binding("l", "open", "Open"),
        Binding("left", "navigate_back", "Back", priority=True),
        Binding("right", "open", "Open", priority=True),
        Binding("space", "pause", "Play/pause"),
        Binding("slash", "search", "Search"),
        Binding("escape", "back", "Back"),
        Binding("a", "append", "Append"),
        Binding("n", "next", "Next"),
        Binding("N", "previous", "Previous"),
        Binding("H", "seek(-5)", "Seek back"),
        Binding("L", "seek(5)", "Seek ahead"),
        Binding("minus", "volume(-5)", "Quieter"),
        Binding("equals_sign", "volume(5)", "Louder"),
        Binding("v", "animation_toggle", "Animation on/off"),
        Binding("x", "animation_shuffle", "Shuffle animation"),
        Binding("s", "animation_save", "Save animation"),
        Binding("S", "animation_recall", "Recall animation"),
        Binding("c", "cover_toggle", "Cover display"),
        Binding("f", "folder", "Folder"),
        Binding("p", "personalize", "Personalize"),
        Binding("ctrl+s", "save_appearance", "Save changes"),
        Binding("r", "rescan", "Rescan"),
        Binding("question_mark", "help", "Help"),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(
        self,
        library: Library,
        folder: Path | None = None,
        player: Player | None = None,
        artwork: str | None = None,
        characters: str | None = None,
    ):
        super().__init__()
        self.library = library
        self.artwork_mode = (
            artwork
            or library.setting("artwork_mode")
            or ("blocks" if os.environ.get("TERM") == "linux" else "auto")
        )
        self.appearance = Appearance.load(library)
        if characters:
            self.appearance = replace(self.appearance, characters=characters)
        self.personalizing = False
        self.appearance_saving = False
        self.appearance_error = ""
        self.preferences_before = self.appearance
        for theme in themes():
            self.register_theme(theme)
        self.theme = f"kirlian-{self.appearance.palette}"
        if NATIVE_SUPPORTED or self.artwork_mode == "native":
            # Kitty placeholder colors encode image IDs. Quantization breaks them.
            self.console = Console(
                color_system="truecolor",
                file=self.console.file,
                force_terminal=True,
                markup=True,
                highlight=False,
                emoji=False,
                legacy_windows=False,
                safe_box=False,
                soft_wrap=False,
                no_color=False,
            )
        self.initial_folder = folder
        self.player = player or Player()
        self.player.on_change = lambda state: self.post_message(PlayerUpdate(state))
        self.tracks: list[Track] = []
        self.albums: list[Album] = []
        self.by_path: dict[str, Track] = {}
        self.rows: list[Row] = []
        self.view = "albums"
        self.view_value = ""
        self.searching = False
        self.saved_view = ("albums", "", 0)
        self.stop_scan = threading.Event()
        self.scanning = False
        self.ready = False
        self.last_player_key: object = None
        self.last_error = ""
        self.cover_key: str | None = None
        self.cover_cache: OrderedDict[str, PILImage.Image | None] = OrderedDict()
        self.cover_revision = 0
        self.palette_key: str | None = None
        self.palette_revision = 0
        self.palette_cache: OrderedDict[str, tuple[str, ...]] = OrderedDict()
        self.saved_animations: list[Variation] = []
        self.recalled_index = -1
        try:
            for code in json.loads(library.setting("saved_animations") or "[]"):
                self.saved_animations.append(Variation.parse(code))
        except (ValueError, TypeError, AttributeError):
            self.saved_animations = []

    def compose(self) -> ComposeResult:
        with Horizontal(id="masthead"):
            yield Brand(self.appearance.logo, id="brand")
            yield Static("", id="search-hint")
        yield Input(placeholder="Search songs, albums, artists…", id="search")
        with Horizontal(id="body"):
            with Vertical(id="navigation"):
                yield Static("LIBRARY", id="nav-heading")
                yield OptionList("Albums", "Artists", "Songs", "Playlists", "Queue", id="nav")
            with Vertical(id="browser"):
                yield Static("", id="breadcrumb")
                with Horizontal(id="collection-header"):
                    yield Static("Albums", id="heading")
                    yield Static("", id="collection-detail")
                yield LibraryTable(id="tracks", cursor_type="row", zebra_stripes=False)
                yield Static("Choose a music folder with f to begin.", id="empty")
            with RecordPane(id="context"):
                yield CoverImage(self.artwork_mode, no_color=self.no_color, id="cover")
                yield Static("", id="cover-placeholder")
                yield Static("LOCAL MUSIC", id="record-details")
                yield Static("", id="record-note")
        with Vertical(id="personalization"):
            yield Static("Make it yours", id="appearance-heading")
            with VerticalScroll(id="appearance-fields"):
                yield Static("", id="appearance-preview")
                for name, label in (
                    ("palette", "Interface palette"),
                    ("motion", "Motion"),
                    ("characters", "Characters"),
                    ("logo", "Header"),
                ):
                    with Horizontal(classes="preference-row"):
                        yield Label(label)
                        yield Select(
                            OPTIONS[name],
                            value=getattr(self.appearance, name),
                            allow_blank=False,
                            id=f"pref-{name}",
                        )
                yield Static(
                    "Interface color changes controls and highlights. "
                    "The ribbon keeps the playing album's colors.",
                    id="appearance-explanation",
                )
                yield Static("", id="appearance-context")
            yield Static("", id="appearance-feedback")
            with Horizontal(id="appearance-buttons"):
                yield Button("Save changes", id="appearance-keep", variant="primary")
                yield Button("Reset", id="appearance-reset")
                yield Button("Cancel", id="appearance-cancel")
        yield Static("", id="status")
        with Vertical(id="playback"):
            with Horizontal(id="now-playing"):
                yield Static("○", id="play-state")
                yield Static(
                    "Nothing playing\nChoose a song from your library.", id="playing-label"
                )
                yield Static("", id="playing-time")
            yield Animation(id="animation")
            yield Progress(id="progress")
        with Horizontal(id="footer"):
            yield Static("", id="shortcuts")
            yield Static("vol 50%", id="volume")

    def on_mount(self) -> None:
        self.query_one("#search").display = False
        self.query_one("#personalization").display = False
        self.query_one("#status").display = False
        if self.artwork_mode == "off":
            self.query_one(CoverImage).display = False
            self.query_one("#cover-placeholder").display = False
        self.apply_appearance()
        table = self.query_one(DataTable)
        table.add_column("Record / song", key="title", width=28)
        table.add_column("Artist / detail", key="detail", width=18)
        table.add_column("Time", key="time", width=6)
        self.query_one("#nav", OptionList).highlighted = 0
        table.focus()
        self.update_footer()
        self.on_resize()
        self.boot()

    @work
    async def boot(self) -> None:
        await self.refresh_library()
        self.status("Starting the playback engine…")
        try:
            await self.player.start()
            self.ready = True
            self.status("")
        except PlaybackError as error:
            self.status(str(error))
        if self.initial_folder:
            self.start_scan(str(self.initial_folder))
        elif not self.library.setting("music_folder"):
            self.action_folder()

    async def refresh_library(self) -> None:
        self.tracks = await asyncio.to_thread(self.library.tracks)
        self.by_path = {track.path: track for track in self.tracks}
        self.albums = albums_from(self.tracks)
        if self.is_running:
            self.render_rows()

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        if isinstance(self.focused, Input) and action not in {
            "back",
            "focus_next",
            "focus_previous",
        }:
            return False
        if isinstance(self.screen, ModalScreen):
            return action in {"focus_next", "focus_previous"}
        if action == "save_appearance":
            return self.personalizing and not self.appearance_saving
        if self.personalizing:
            if self.appearance_saving:
                return action in {"focus_next", "focus_previous"}
            return action in {"back", "focus_next", "focus_previous"}
        return True

    def on_resize(self, event: events.Resize | None = None) -> None:
        if self.is_mounted and self.query("#body"):
            size = event.size if event else self.size
            width = size.width
            self.query_one("#body").screen.set_class(size.height < 30, "compact")
            self.query_one(Brand).configure(
                self.appearance.logo, size.height < 30, self.appearance.characters == "ascii"
            )
            self.query_one("#context").display = width >= 110
            if self.personalizing:
                self.update_appearance_feedback(height=size.height)
            self.call_after_refresh(self.size_columns)
            self.call_after_refresh(self.update_context)

    def size_columns(self) -> None:
        if not self.is_running or not self.query("#tracks"):
            return
        table = self.query_one(DataTable)
        # Reserve padding, the time column, and a vertical scrollbar at 80 columns.
        available = max(16, table.size.width - 14)
        if table.columns:
            key = (available, self.view, self.searching)
            if key == getattr(self, "_column_layout", None):
                return
            self._column_layout = key
            in_album = self.view == "album" and not self.searching
            table.columns["title"].width = 6 if in_album else int(available * 0.65)
            table.columns["detail"].width = available - table.columns["title"].width
            title = (
                "TITLE"
                if self.searching
                else "ALBUM"
                if self.view in {"albums", "artist"}
                else "ARTIST"
                if self.view == "artists"
                else "SONG"
            )
            table.columns["title"].label = Text("#" if in_album else title)
            table.columns["detail"].label = Text(
                "TITLE"
                if in_album
                else "TYPE / ARTIST"
                if self.searching
                else ""
                if self.view == "artists"
                else "ARTIST"
            )
            table.columns["time"].label = Text("TIME", justify="right")
            table.refresh_columns()

    def status(self, message: str) -> None:
        if self.is_running:
            status = self.query_one("#status", Static)
            status.update(Text(display_text(message)))
            status.display = bool(message)

    def key_hints(self, pairs: list[tuple[str, str]]) -> Text:
        text = Text()
        for index, (key, label) in enumerate(pairs):
            if index:
                text.append("   ")
            text.append(key, self.appearance.accent)
            text.append(f" {label}", QUIET)
        return text

    def update_footer(self) -> None:
        self.update_text("#search-hint", self.key_hints([("/", "search"), ("p", "personalize")]))
        row = self.selected()
        state = getattr(self, "display_state", self.player.state)
        hint = [
            ("enter", "open" if row and row.kind in {"album", "artist"} else "play"),
            ("space", "pause" if not (state.paused or state.idle) else "play"),
            ("x", "pattern"),
            ("?", "help"),
            ("q", "quit"),
        ]
        if self.searching:
            hint = [("enter", "open/play"), ("tab", "results"), ("esc", "back")]
        if self.personalizing:
            hint = [("tab", "move"), ("enter", "choose"), ("ctrl+s", "save"), ("esc", "cancel")]
        self.update_text("#shortcuts", self.key_hints(hint))

    def update_text(self, selector: str, content: Text | str) -> None:
        """Fixed-size labels should not relayout the screen on every player event."""
        widget = self.query_one(selector, Static)
        if widget.content != content:
            widget.update(content, layout=False)

    def album(self, album_id: str) -> Album | None:
        return next((album for album in self.albums if album.id == album_id), None)

    def track_row(self, track: Track, detail: str | None = None) -> Row:
        marker = "> " if self.player.state.path == track.path and not self.player.state.idle else ""
        unavailable = " [unavailable]" if not track.available else ""
        return Row(
            "track",
            track.path,
            marker + track.title + unavailable,
            detail if detail is not None else track.artist,
            clock(track.duration),
        )

    def render_rows(self, position: int | None = None) -> None:
        if not self.is_running or not self.query("#tracks"):
            return
        table = self.query_one(DataTable)
        previous = self.selected()
        old_position = table.cursor_row
        rows: list[Row] = []
        heading = self.view.title()
        if self.searching:
            query = self.query_one("#search", Input).value.casefold().strip()
            heading = "Search"
            if query:
                rows.extend(
                    Row("album", a.id, a.title, f"Album · {a.artist}")
                    for a in self.albums
                    if query in f"{a.title} {a.artist}".casefold()
                )
                artists = sorted({t.artist for t in self.tracks}, key=str.casefold)
                rows.extend(Row("artist", a, a, "Artist") for a in artists if query in a.casefold())
                rows.extend(
                    self.track_row(t, f"Song · {t.artist} · {t.album}")
                    for t in self.tracks
                    if query in f"{t.title} {t.artist} {t.album}".casefold()
                )
        elif self.view == "albums":
            rows = [
                Row("album", a.id, a.title, a.artist, clock(sum(t.duration for t in a.tracks)))
                for a in self.albums
            ]
        elif self.view == "artists":
            rows = [
                Row("artist", a, a)
                for a in sorted({t.artist for t in self.tracks}, key=str.casefold)
            ]
        elif self.view == "songs":
            rows = [
                self.track_row(t) for t in sorted(self.tracks, key=lambda t: t.title.casefold())
            ]
        elif self.view == "album":
            album = self.album(self.view_value)
            heading = album.title if album else "Album unavailable"
            if album:
                rows = [
                    self.track_row(t, f"{t.disc}.{t.track:02d} · {t.artist}") for t in album.tracks
                ]
        elif self.view == "artist":
            heading = self.view_value
            rows = [
                Row("album", a.id, a.title, a.artist)
                for a in self.albums
                if any(t.artist == self.view_value for t in a.tracks)
            ]
        elif self.view == "queue":
            for index, item in enumerate(self.player.state.playlist):
                track = self.by_path.get(item["filename"])
                title = track.title if track else display_text(Path(item["filename"]).name)
                marker = "> " if index == self.player.state.index else ""
                rows.append(
                    Row(
                        "queue",
                        str(index),
                        marker + title,
                        track.artist if track else "",
                        clock(track.duration) if track else "",
                    )
                )
        self.rows = rows
        table.clear()
        for index, row in enumerate(rows):
            if self.view == "album" and not self.searching and row.kind == "track":
                track = self.by_path[row.value]
                marker = ">" if row.title.startswith("> ") else " "
                number = (
                    f"{track.disc}.{track.track:02d}" if track.disc > 1 else f"{track.track:02d}"
                )
                table.add_row(
                    Text(f"{marker} {number}"),
                    Text(track.title, no_wrap=True, overflow="ellipsis"),
                    Text(row.duration, justify="right"),
                    key=str(index),
                )
            else:
                table.add_row(
                    Text(row.title, no_wrap=True, overflow="ellipsis"),
                    Text(row.detail, no_wrap=True, overflow="ellipsis"),
                    Text(row.duration, justify="right"),
                    key=str(index),
                )
        target = old_position if position is None else position
        if position is None and previous:
            target = next(
                (
                    i
                    for i, r in enumerate(rows)
                    if (r.kind, r.value) == (previous.kind, previous.value)
                ),
                target,
            )
        if rows:
            table.move_cursor(row=min(max(0, target), len(rows) - 1))
        self.query_one("#heading", Static).update(Text(heading))
        album = self.album(self.view_value) if self.view == "album" and not self.searching else None
        breadcrumb = self.query_one("#breadcrumb", Static)
        breadcrumb.update(Text(f"Albums / {album.artist}" if album else ""))
        breadcrumb.display = album is not None
        self.query_one("#collection-detail", Static).update(
            Text(
                f"{album.tracks[0].year + ' · ' if album.tracks[0].year else ''}"
                f"{len(album.tracks)} {'song' if len(album.tracks) == 1 else 'songs'} · "
                f"{clock(sum(t.duration for t in album.tracks))}"
                if album
                else f"{len(rows)} {'results' if self.searching else self.view}"
            )
        )
        empty = self.query_one("#empty", Static)
        empty.display = not rows
        empty.update(
            "Saved playlists aren't available yet. Use Queue to line up your music."
            if self.view == "playlists"
            else "No matching music."
            if self.searching
            else "Queue is empty. Append with a, or play a track."
            if self.view == "queue"
            else "No music here yet. Press f to choose a folder, or r to rescan."
        )
        self.size_columns()
        self.update_context()
        self.update_footer()

    def selected(self) -> Row | None:
        index = self.query_one(DataTable).cursor_row
        return self.rows[index] if 0 <= index < len(self.rows) else None

    def update_context(self) -> None:
        if not self.is_running or not self.query("#tracks"):
            return
        row = self.selected()
        track = None
        album = None
        if row:
            if row.kind == "track":
                track = self.by_path.get(row.value)
            elif row.kind == "queue":
                index = int(row.value)
                playlist = self.player.state.playlist
                if index < len(playlist):
                    track = self.by_path.get(playlist[index]["filename"])
            album = (
                self.album(track.album_id)
                if track
                else (self.album(row.value) if row.kind == "album" else None)
            )
        details = Text()
        note = Text()
        if album:
            details.append(album.title + "\n", style="bold #e5ddcd")
            details.append(album.artist + "\n\n")
            year = album.tracks[0].year
            formats = " / ".join(sorted({t.format for t in album.tracks}))
            details.append(f"{year + ' · ' if year else ''}{formats}\n")
            details.append(
                f"{len(album.tracks)} {'song' if len(album.tracks) == 1 else 'songs'} · "
                f"{clock(sum(t.duration for t in album.tracks))}"
            )
            if track:
                note.append("ON THIS RECORD\n\n", style="#958c98")
                note.append(track.title + "\n", style="#e5ddcd")
                note.append(f"{track.disc}.{track.track:02d} · {clock(track.duration)}")
        else:
            details.append(f"LOCAL MUSIC\n\n{len(self.albums)} albums\n{len(self.tracks)} songs")
        self.query_one("#record-details", Static).update(details)
        record_note = self.query_one("#record-note", Static)
        record_note.update(note)
        record_note.display = bool(note.plain) and self.size.height >= 48
        if not self.query_one("#context").display or self.query_one(CoverImage).mode == "off":
            return
        key = album.id if album else ""
        if key == self.cover_key:
            return
        self.cover_key = key
        self.cover_revision += 1
        revision = self.cover_revision
        if album:
            if key in self.cover_cache:
                self.cover_cache.move_to_end(key)
                self.show_cover(self.cover_cache[key])
            else:
                # Hide stale art without throwing away reusable native placements.
                self.query_one(CoverImage).display = False
                label = self.query_one("#cover-placeholder", Static)
                label.update("Loading cover…")
                label.display = True
                self.fetch_cover(key, tuple(t.path for t in album.tracks), revision)
        else:
            self.show_cover(None, "")

    def show_cover(
        self, image: PILImage.Image | None, placeholder: str = "No cover in these files"
    ) -> None:
        cover = self.query_one("#cover", CoverImage)
        cover.image = image
        cover.display = image is not None and cover.mode != "off"
        label = self.query_one("#cover-placeholder", Static)
        label.update(placeholder)
        label.display = image is None and cover.mode != "off"

    @work(group="artwork", exclusive=True)
    async def fetch_cover(self, key: str, paths: tuple[str, ...], revision: int) -> None:
        # Debounce fast navigation. Stale decodes never replace a newer selection.
        await asyncio.sleep(0.04)
        image = await asyncio.to_thread(load_artwork, paths)
        if not self.is_running or revision != self.cover_revision:
            return
        self.cover_cache[key] = image
        while len(self.cover_cache) > 12:
            self.cover_cache.popitem(last=False)
        self.show_cover(image)

    def on_data_table_row_highlighted(self) -> None:
        self.update_context()
        self.update_footer()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self.searching = False
        self.query_one("#search").display = False
        self.view = ("albums", "artists", "songs", "playlists", "queue")[event.option_index]
        self.view_value = ""
        self.render_rows(0)
        self.query_one(DataTable).focus()
        self.update_footer()

    def on_data_table_row_selected(self) -> None:
        self.open_selected()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "search":
            self.open_selected()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "search" and self.searching:
            self.render_rows(0)

    def open_selected(self) -> None:
        row = self.selected()
        if not row:
            return
        if row.kind in {"album", "artist"}:
            self.searching = False
            self.query_one("#search").display = False
            self.view, self.view_value = row.kind, row.value
            self.render_rows(0)
            self.update_footer()
        elif row.kind == "track":
            track = self.by_path[row.value]
            if not track.available:
                self.status("This file is unavailable. Restore it and rescan with r.")
                return
            album = self.album(track.album_id)
            if album:
                paths = [t.path for t in album.tracks]
                self.perform(self.player.play(paths, paths.index(track.path)))
        elif row.kind == "queue":
            self.perform(self.player.jump(int(row.value)))
        self.query_one(DataTable).focus()

    @work(group="playback")
    async def perform(self, operation) -> None:
        try:
            await operation
        except PlaybackError as error:
            self.status(str(error))

    def action_open(self) -> None:
        if self.focused is self.query_one("#nav"):
            self.query_one("#nav", OptionList).action_select()
        else:
            self.open_selected()

    def action_down(self) -> None:
        if isinstance(self.focused, (DataTable, OptionList)):
            self.focused.action_cursor_down()

    def action_up(self) -> None:
        if isinstance(self.focused, (DataTable, OptionList)):
            self.focused.action_cursor_up()

    def action_back(self) -> None:
        if self.personalizing:
            self.finish_personalizing(False)
            return
        if self.searching:
            self.searching = False
            self.query_one("#search").display = False
            self.view, self.view_value, position = self.saved_view
            self.render_rows(position)
            self.update_footer()
        else:
            self.view, self.view_value = "albums", ""
            self.render_rows(0)
        self.query_one(DataTable).focus()

    def action_navigate_back(self) -> None:
        self.action_back()

    def action_search(self) -> None:
        if not self.searching:
            self.saved_view = (self.view, self.view_value, self.query_one(DataTable).cursor_row)
        self.searching = True
        search = self.query_one("#search", Input)
        search.display = True
        search.value = ""
        search.focus()
        self.render_rows(0)
        self.update_footer()

    def action_append(self) -> None:
        row = self.selected()
        paths = []
        if row and row.kind == "track":
            paths = [row.value]
        elif row and row.kind == "album" and (album := self.album(row.value)):
            paths = [t.path for t in album.tracks]
        if paths:
            self.append_paths(paths)

    @work(group="playback")
    async def append_paths(self, paths: list[str]) -> None:
        try:
            await self.player.append(paths)
            self.status(
                f"Appended {len(paths)} track(s). Open Queue to inspect; "
                "Space starts an idle queue."
            )
        except PlaybackError as error:
            self.status(str(error))

    def action_pause(self) -> None:
        self.perform(self.player.toggle_pause())

    def action_next(self) -> None:
        self.perform(self.player.control("playlist-next", "weak"))

    def action_previous(self) -> None:
        self.perform(self.player.control("playlist-prev", "weak"))

    def action_seek(self, seconds: int) -> None:
        self.perform(self.player.control("seek", seconds, "relative+exact"))

    def action_volume(self, amount: int) -> None:
        value = min(100, max(0, self.player.state.volume + amount))
        self.perform(self.player.control("set_property", "volume", value))

    def action_folder(self) -> None:
        if self.scanning:
            self.status(
                "Indexing is still running. You can choose another folder when it finishes."
            )
            return
        self.push_screen(FolderDialog(), self.start_scan)

    def start_scan(self, folder: str | None) -> None:
        if folder and not self.scanning:
            self.scanning = True
            self.stop_scan.clear()
            self.status("Indexing music… You can keep browsing and listening.")
            self.scan(folder)

    @work(thread=True, group="scan")
    def scan(self, folder: str) -> None:
        self.library.scan(Path(folder), lambda p: self.post_message(ScanUpdate(p)), self.stop_scan)

    async def on_scan_update(self, message: ScanUpdate) -> None:
        progress = message.progress
        self.cover_cache.clear()
        self.cover_key = None
        self.palette_cache.clear()
        self.palette_key = None
        self.palette_revision += 1
        await self.refresh_library()
        self.scanning = not progress.done
        self.update_ribbon_palette(getattr(self, "display_state", self.player.state))
        self.status(
            progress.error
            or f"{'Indexed' if progress.done else 'Indexing'} {progress.indexed} files · "
            f"{progress.skipped} unreadable files/folders skipped"
        )

    def action_rescan(self) -> None:
        if self.scanning:
            self.status("Indexing is already running.")
        elif folder := self.library.setting("music_folder"):
            self.start_scan(folder)
        else:
            self.action_folder()

    def on_player_update(self, message: PlayerUpdate) -> None:
        if not self.is_running:
            return
        state = message.state
        self.display_state = state
        track = self.by_path.get(state.path)
        title = track.title if track else display_text(Path(state.path).name) if state.path else ""
        artist = track.artist if track else "Local music"
        mode = (
            "Loading"
            if state.loading
            else "Stopped"
            if state.idle
            else "Paused"
            if state.paused
            else "Playing"
        )
        symbol = "○" if state.idle else "·" if state.loading else "Ⅱ" if state.paused else "▶"
        if self.appearance.characters == "ascii":
            symbol = "o" if state.idle else "." if state.loading else "||" if state.paused else ">"
        self.update_text("#play-state", Text(symbol, self.appearance.accent))
        self.update_text(
            "#playing-label",
            Text.assemble(
                (title or "Nothing playing", INK),
                (f"\n{artist} · {mode}" if title else "\nChoose a song from your library.", QUIET),
            ),
        )
        self.update_text(
            "#playing-time",
            Text.assemble(
                (clock(state.position), self.appearance.accent),
                (f" / {clock(state.duration)}", QUIET),
            )
            if title or state.duration
            else Text(""),
        )
        self.update_text("#volume", f"vol {state.volume:.0f}%")
        self.query_one(Progress).set_progress(state.position, state.duration)
        animation = self.query_one(Animation)
        previous_serial = animation.clock.serial
        animation.observe(state)
        self.update_ribbon_palette(state)
        if animation.clock.serial != previous_serial and not self.scanning:
            self.status("")
        key = (
            state.path,
            state.index,
            state.idle,
            tuple(item.get("id") for item in state.playlist),
        )
        if key != self.last_player_key:
            self.last_player_key = key
            if not isinstance(self.screen, ModalScreen):
                self.render_rows()
        if state.error and state.error != self.last_error:
            self.status(state.error)
        self.last_error = state.error
        if self.personalizing:
            self.update_appearance_feedback()
        self.update_footer()

    def update_ribbon_palette(self, state: PlaybackState) -> None:
        track = self.by_path.get(state.path)
        album = self.album(track.album_id) if track else None
        key = (album.id if album else f"file:{state.path}") if state.path and not state.idle else ""
        if key == self.palette_key:
            return
        self.palette_key = key
        self.palette_revision += 1
        self.query_one(Animation).set_palette(self.palette_cache.get(key, ()))
        if not key:
            return
        if key in self.palette_cache:
            self.palette_cache.move_to_end(key)
            return
        paths = tuple(track.path for track in album.tracks) if album else (state.path,)
        self.fetch_palette(key, paths, self.palette_revision)

    @work(group="album-palette", exclusive=True)
    async def fetch_palette(self, key: str, paths: tuple[str, ...], revision: int) -> None:
        # Playback owns the palette, independent of the browsed album or pane visibility.
        await asyncio.sleep(0.12)
        if key in self.cover_cache:
            image = self.cover_cache[key]
        else:
            image = await asyncio.to_thread(load_artwork, paths)
        colors = await asyncio.to_thread(extract_palette, image)
        if not self.is_running or revision != self.palette_revision:
            return
        self.palette_cache[key] = colors
        while len(self.palette_cache) > 64:
            self.palette_cache.popitem(last=False)
        self.query_one(Animation).set_palette(colors)

    def apply_appearance(self) -> None:
        self.theme = f"kirlian-{self.appearance.palette}"
        self.query_one(Animation).configure(self.appearance)
        progress = self.query_one(Progress)
        progress.accent = self.appearance.accent
        progress.ascii = self.appearance.characters == "ascii"
        progress.refresh()
        self.query_one(Brand).configure(
            self.appearance.logo, self.size.height < 30, self.appearance.characters == "ascii"
        )
        if self.is_running:
            self.on_player_update(PlayerUpdate(getattr(self, "display_state", self.player.state)))

    def action_personalize(self) -> None:
        self.personalizing = True
        self.appearance_error = ""
        self.preferences_before = self.appearance
        for name in OPTIONS:
            select = self.query_one(f"#pref-{name}", Select)
            with select.prevent(Select.Changed):
                select.value = getattr(self.appearance, name)
        self.query_one("#body").display = False
        self.query_one("#personalization").display = True
        self.update_footer()
        self.update_appearance_feedback()
        self.query_one("#pref-palette", Select).focus()

    def appearance_from_fields(self) -> Appearance:
        return Appearance(
            **{name: self.query_one(f"#pref-{name}", Select).value for name in OPTIONS}
        )

    def update_appearance_feedback(self, height: int | None = None) -> None:
        accent, selected = PALETTES[self.appearance.palette]
        preview = Text.assemble(
            (f" {self.appearance.palette.title()} ", f"{INK} on {selected}"),
            ("  Selected row   ", QUIET),
            ("/ search   p personalize", accent),
        )
        self.update_text("#appearance-preview", preview)
        notes = []
        if self.no_color:
            notes.append("Color is disabled by NO_COLOR; the palette will display in grayscale.")
        state = getattr(self, "display_state", self.player.state)
        if self.appearance.motion == "gentle" and (state.paused or state.idle or state.loading):
            notes.append(
                "The ribbon moves during playback; it stays still while paused or stopped."
            )
        if (self.size.height if height is None else height) < 30 and self.appearance.logo == "auto":
            notes.append("This window uses the small header. The drawn logo needs 30 rows.")
        context = self.query_one("#appearance-context", Static)
        content = "\n".join(notes)
        if context.content != content:
            context.update(content)
        context.display = bool(content)
        if self.appearance_saving:
            feedback = "Saving changes…"
        elif self.appearance_error:
            feedback = self.appearance_error
        elif self.appearance != self.preferences_before:
            feedback = "Unsaved preview · Ctrl+S saves · Esc cancels"
        else:
            feedback = "No changes yet · Ctrl+S saves · Esc cancels"
        widget = self.query_one("#appearance-feedback", Static)
        if widget.content != feedback:
            widget.update(feedback)

    def on_select_changed(self, event: Select.Changed) -> None:
        if not self.personalizing or self.appearance_saving or not isinstance(event.value, str):
            return
        name = (event.select.id or "").removeprefix("pref-")
        if name in OPTIONS:
            self.appearance = self.appearance_from_fields()
            self.appearance_error = ""
            self.apply_appearance()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if self.appearance_saving:
            return
        if event.button.id == "appearance-keep":
            self.finish_personalizing(True)
        elif event.button.id == "appearance-cancel":
            self.finish_personalizing(False)
        elif event.button.id == "appearance-reset":
            self.appearance_error = ""
            self.appearance = Appearance()
            for name in OPTIONS:
                select = self.query_one(f"#pref-{name}", Select)
                with select.prevent(Select.Changed):
                    select.value = getattr(self.appearance, name)
            self.apply_appearance()

    def action_save_appearance(self) -> None:
        self.finish_personalizing(True)

    def finish_personalizing(self, keep: bool) -> None:
        if not self.personalizing or self.appearance_saving:
            return
        if keep:
            # Read the controls, not a possibly queued Select.Changed message.
            self.appearance = self.appearance_from_fields()
            self.appearance_saving = True
            self.appearance_error = ""
            self.set_appearance_controls_disabled(True)
            self.apply_appearance()
            self.persist_appearance(self.appearance)
        else:
            self.appearance = self.preferences_before
            self.close_personalization(False)

    def set_appearance_controls_disabled(self, disabled: bool) -> None:
        for control in self.query("#personalization Select, #personalization Button"):
            control.disabled = disabled

    @work(group="appearance-save", exclusive=True)
    async def persist_appearance(self, appearance: Appearance) -> None:
        try:
            await asyncio.to_thread(appearance.save, self.library)
        except (sqlite3.Error, OSError):
            self.appearance_error = "Could not save. Your preview is here; retry or Cancel."
        finally:
            self.appearance_saving = False
            self.set_appearance_controls_disabled(False)
        if self.appearance_error:
            self.update_appearance_feedback()
            self.query_one("#appearance-keep", Button).focus()
        else:
            self.close_personalization(True)

    def close_personalization(self, saved: bool) -> None:
        self.personalizing = False
        self.apply_appearance()
        self.query_one("#personalization").display = False
        self.query_one("#body").display = True
        self.query_one(DataTable).focus()
        self.update_footer()
        self.status(
            "Appearance saved for next time." if saved else "Preview canceled; nothing saved."
        )

    def action_animation_toggle(self) -> None:
        motion = "gentle" if self.appearance.motion == "off" else "off"
        self.appearance = replace(self.appearance, motion=motion)
        self.appearance.save(self.library)
        self.apply_appearance()
        self.status("Motion on." if motion == "gentle" else "Motion off. Press v to enable.")

    def action_animation_shuffle(self) -> None:
        animation = self.query_one(Animation)
        animation.shuffle()
        self.status(f"{animation.clock.variation.label} · s keeps this pattern · S recalls saved")

    def action_animation_save(self) -> None:
        variation = self.query_one(Animation).clock.variation
        if variation not in self.saved_animations:
            self.saved_animations.append(variation)
            self.library.set_setting(
                "saved_animations", json.dumps([v.code for v in self.saved_animations])
            )
        self.status(f"Saved {variation.label} · S recalls saved patterns")

    def action_animation_recall(self) -> None:
        if not self.saved_animations:
            self.status("No saved animations yet. Press s to keep the current one.")
            return
        self.recalled_index = (self.recalled_index + 1) % len(self.saved_animations)
        variation = self.saved_animations[self.recalled_index]
        self.query_one(Animation).select(variation)
        self.status(
            f"Saved {self.recalled_index + 1}/{len(self.saved_animations)} · {variation.label}"
        )

    def action_cover_toggle(self) -> None:
        cover = self.query_one(CoverImage)
        cover.toggle()
        if cover.mode == "native" and self.console.color_system != "truecolor":
            self.console = Console(
                color_system="truecolor",
                file=self.console.file,
                force_terminal=True,
                no_color=False,
                highlight=False,
            )
        self.cover_key = None
        self.update_context()
        self.library.set_setting("artwork_mode", cover.mode)
        self.status(
            "Cover display: compatible blocks. Press c to try terminal graphics."
            if cover.mode == "blocks"
            else "Cover display: terminal graphics. If blank, press c for compatible blocks."
        )

    def action_help(self) -> None:
        self.notify(
            "j/k or arrows move · h back · l/Enter open/play · Tab changes pane\n"
            "Space pause · a append · n/N next/previous · H/L seek 5s · -/= volume\n"
            "/ search · Esc back · f folder · p personalize · r rescan · q quit\n"
            "x shuffle animation · v motion on/off · s save · S recall saved\n"
            "c switch cover display (remembered)\n"
            "Typing in search or folder fields never triggers playback shortcuts.",
            title="Keyboard controls",
            timeout=12,
        )

    async def action_quit(self) -> None:
        self.stop_scan.set()
        await self.player.close()
        self.exit()

    async def on_unmount(self) -> None:
        self.stop_scan.set()
        await self.player.close()
