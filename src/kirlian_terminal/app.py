# SPDX-License-Identifier: GPL-3.0-or-later
"""Album browsing and playback UI. Filesystem and player work run in workers."""

from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import sys
import threading
import webbrowser
from collections import OrderedDict
from collections.abc import Callable
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
from .facts import (
    PROVIDERS,
    Credentials,
    Fact,
    FactCache,
    FactsConfig,
    FactsError,
    Provider,
    fact_key,
    request_facts,
)
from .graphics import NATIVE_SUPPORTED
from .library import Album, Library, ScanProgress, Track, albums_from, display_text
from .palette import extract_palette
from .playback import PlaybackError, PlaybackState, Player
from .playlists import Entry, Playlist, Playlists
from .visuals import Animation, Progress, TitleRhythm


def clock(seconds: float) -> str:
    minutes, seconds = divmod(max(0, int(seconds)), 60)
    return f"{minutes}:{seconds:02d}"


def scan_message(progress: ScanProgress) -> str:
    if progress.error:
        return progress.error
    if not progress.done or progress.indexed:
        return (
            f"{'Indexed' if progress.done else 'Indexing'} {progress.indexed} files · "
            f"{progress.skipped} unreadable files/folders skipped"
        )
    if progress.blocked:
        where = (
            "allow your terminal in System Settings › Privacy & Security › Files and Folders"
            if sys.platform == "darwin"
            else "check the folder permissions"
        )
        return (
            f"No music indexed: permission denied for {progress.blocked} folder(s). "
            f"Press f to choose another folder, or {where} and press r."
        )
    return "No music files found in this folder. Press f to choose another folder."


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


class NameDialog(ModalScreen[str | None]):
    """Names are stored as typed; display_text guards them when drawn."""

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, title: str, value: str = "") -> None:
        super().__init__()
        self.title_text = title
        self.value = value

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog"):
            yield Label(self.title_text)
            yield Input(value=self.value, placeholder="Playlist name", id="playlist-name")
            yield Static("Enter saves · Esc cancels", classes="dialog-hint")

    def on_mount(self) -> None:
        self.query_one(Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if name := event.value.strip():
            self.dismiss(name)

    def action_cancel(self) -> None:
        self.dismiss(None)


class PlaylistPicker(ModalScreen[int | None]):
    """Returns a playlist id, or 0 to create a new playlist."""

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, playlists: list[Playlist], count: int) -> None:
        super().__init__()
        self.playlists = playlists
        self.count = count

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog"):
            yield Label(f"Add {self.count} {'song' if self.count == 1 else 'songs'} to…")
            yield OptionList(
                "+ New playlist…",
                *(Text(display_text(p.name)) for p in self.playlists),
                id="playlist-choices",
            )
            yield Static("Enter chooses · Esc cancels", classes="dialog-hint")

    def on_mount(self) -> None:
        self.query_one(OptionList).focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        index = event.option_index
        self.dismiss(self.playlists[index - 1].id if index else 0)

    def action_cancel(self) -> None:
        self.dismiss(None)


class ConfirmDialog(ModalScreen[bool]):
    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, message: str, confirm: str) -> None:
        super().__init__()
        self.message = message
        self.confirm = confirm

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog"):
            yield Static(Text(self.message))
            with Horizontal(classes="dialog-buttons"):
                yield Button(self.confirm, id="confirm", variant="error")
                yield Button("Cancel", id="cancel")

    def on_mount(self) -> None:
        self.query_one("#cancel", Button).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "confirm")

    def action_cancel(self) -> None:
        self.dismiss(False)


class KeyDialog(ModalScreen[tuple[str, bool] | None]):
    """Add or replace one provider's key. Returns (key, keep in keychain)."""

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, provider: Provider, source: str) -> None:
        super().__init__()
        self.provider = provider
        self.source = source

    def compose(self) -> ComposeResult:
        p = self.provider
        with Vertical(classes="dialog"):
            yield Label(f"{p.name} API key")
            note = {
                "environment": f"{p.environment} is set in your environment and takes "
                "precedence; a key saved here is used once it is unset.",
                "keychain": "Replacing the saved key. The old one is overwritten.",
                "session": "Replacing this session's key.",
            }.get(self.source, f"Create one at {p.signup}. {p.name} bills your account.")
            yield Static(note, classes="dialog-hint")
            yield Input(password=True, placeholder=f"{p.name} API key", id="facts-key")
            yield Static("", id="facts-error")
            with Horizontal(classes="dialog-buttons"):
                yield Button("Save to keychain", id="keep", variant="primary")
                yield Button("This session only", id="session")
                yield Button("Cancel", id="cancel")

    def on_mount(self) -> None:
        self.query_one(Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        self.choose("keep")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        self.choose(event.button.id or "cancel")

    def choose(self, choice: str) -> None:
        if choice == "cancel":
            self.dismiss(None)
            return
        key = self.query_one(Input).value.strip()
        if not key:
            self.query_one("#facts-error", Static).update("Paste a key, or press Esc.")
            return
        self.dismiss((key, choice == "keep"))

    def action_cancel(self) -> None:
        self.dismiss(None)


class ModelDialog(ModalScreen[str | None]):
    """Pick the model that writes the notes. Returns a model name, "" for the default."""

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, provider: Provider, current: str) -> None:
        super().__init__()
        self.provider = provider
        self.current = current

    def compose(self) -> ComposeResult:
        p = self.provider
        with Vertical(classes="dialog"):
            yield Label(f"Which {p.name} model writes your notes?")
            yield Static(
                f"{p.name} searches the web, then this model reads the pages and writes the "
                "notes. Larger models usually find better stories and readings, take longer, "
                "and cost more per song. This changes song notes only.",
                classes="dialog-hint",
            )
            options = [
                Text.assemble(
                    ("● " if model == self.current else "  ", self.app.appearance.accent),
                    (model, f"bold {INK}"),
                    ("  default" if model == p.model else "", QUIET),
                    f"\n    {about}",
                )
                for model, about in p.models
            ]
            options.append(Text("  Another model…\n    Type any model name it offers"))
            yield OptionList(*options, id="model-choices")
            yield Input(placeholder=f"{p.name} model name", id="facts-model")

    def on_mount(self) -> None:
        choices = self.query_one(OptionList)
        names = [model for model, _ in self.provider.models]
        known = self.current in names
        choices.highlighted = names.index(self.current) if known else len(names)
        model_input = self.query_one(Input)
        model_input.display = not known
        model_input.value = "" if known else self.current
        choices.focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        models = self.provider.models
        if event.option_index < len(models):
            model = models[event.option_index][0]
            self.dismiss("" if model == self.provider.model else model)
        else:
            model_input = self.query_one(Input)
            model_input.display = True
            model_input.focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        model = event.value.strip()
        self.dismiss("" if model == self.provider.model else model)

    def action_cancel(self) -> None:
        self.dismiss(None)


class FactsSettings(ModalScreen[None]):
    """Song-notes providers in the order they are asked, with keys and models.

    Rows are sorted by role (primary, fallbacks, then unused), so moving a provider
    moves its row, and the selection follows it. The line under the table explains
    the selected provider and lists only the actions that apply to it.
    """

    BINDINGS = [
        Binding("escape", "close", "Close"),
        Binding("enter", "key", "Add or replace key", priority=True),
        Binding("space", "use", "Use / stop using"),
        Binding("J,shift+down", "move(1)", "Move down"),
        Binding("K,shift+up", "move(-1)", "Move up"),
        Binding("j", "cursor(1)", "Down", show=False),
        Binding("k", "cursor(-1)", "Up", show=False),
        *(Binding(str(n), f"place({n})", f"Make #{n}", show=False) for n in range(1, 6)),
        Binding("m", "model", "Model"),
        Binding("d", "forget", "Remove key"),
        Binding("t", "toggle", "Notes on/off"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.row_ids: list[str] = list(PROVIDERS)
        self.selected_id = self.row_ids[0]
        self.config = FactsConfig()
        self.sources: dict[str, str] = {}

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog", id="facts-settings"):
            yield Label("Song notes · Behind the record")
            yield Static("", id="facts-state")
            yield Static(
                "Providers are asked from the top. The primary answers every new song; a "
                "fallback is asked only if the ones above it fail. Sent: title, artist, "
                "album, year. Never: audio, artwork, or file paths.",
                classes="dialog-hint",
            )
            yield DataTable(id="facts-providers", cursor_type="row", zebra_stripes=False)
            yield Static("", id="facts-detail")
            yield Static("", id="facts-actions")
            yield Static("", id="facts-note")

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        for label in ("Role", "Provider", "Key", "Writes notes with"):
            table.add_column(label)
        self.app.refresh_facts_settings(self)
        table.focus()

    @property
    def provider(self) -> Provider:
        return PROVIDERS[self.selected_id]

    def role(self, provider_id: str) -> str:
        order = self.config.order
        if provider_id not in order:
            return "Not used"
        position = order.index(provider_id)
        return "Primary" if position == 0 else f"Fallback {position}"

    def key_label(self, p: Provider) -> str:
        return {
            "keychain": "Saved in keychain",
            "session": "This session only",
            "environment": f"From shell ({p.environment})",
        }.get(self.sources.get(p.id, ""), "No key")

    def show(self, config: FactsConfig, sources: dict[str, str], on: bool, note: str) -> None:
        self.config, self.sources = config, sources
        self.row_ids = config.order + [p for p in PROVIDERS if p not in config.order]
        accent = self.app.appearance.accent
        table = self.query_one(DataTable)
        table.clear()
        for provider_id in self.row_ids:
            p = PROVIDERS[provider_id]
            used = provider_id in config.order
            table.add_row(
                Text(self.role(provider_id), f"bold {accent}" if used else QUIET),
                Text(p.name, INK if used else QUIET),
                Text(self.key_label(p), INK if sources.get(p.id) else QUIET),
                Text(config.model(p) or "its own model", INK if config.model(p) else QUIET),
                key=provider_id,
            )
        table.move_cursor(row=self.row_ids.index(self.selected_id))
        self.query_one("#facts-state", Static).update(
            Text.assemble(
                ("Notes are ", QUIET),
                ("on" if on else "off", f"bold {accent}" if on else "bold"),
                ("  ·  ", QUIET),
                ("t", "bold"),
                (f" to turn {'off' if on else 'on'}", QUIET),
            )
        )
        self.query_one("#facts-note", Static).update(Text(note, accent))
        self.describe()

    def describe(self) -> None:
        """Explain the selected provider and list the actions that apply to it."""
        p = self.provider
        order = self.config.order
        model = self.config.model(p)
        if p.id not in order:
            role = "Not used. Press space to add it as the last fallback."
        elif order.index(p.id) == 0:
            role = "Primary: asked first for every new song."
        else:
            above = PROVIDERS[order[order.index(p.id) - 1]].name
            role = f"Fallback: asked only if {above} fails."
        writer = (
            f"Notes are written by {model}."
            if model
            else f"{p.name} picks the model that writes the notes."
        )
        self.query_one("#facts-detail", Static).update(
            Text.assemble((p.name, f"bold {INK}"), "  ", (f"{role} {writer}", QUIET))
        )
        actions = [("enter", "replace key" if self.sources.get(p.id) else "add key")]
        if p.id in order:
            actions.append(("space", "stop using"))
            if len(order) > 1:
                actions.append(("K/J or 1-5", "move up/down"))
        else:
            actions.append(("space", "use as fallback"))
            actions.append(("1", "make primary"))
        if p.models:
            actions.append(("m", "change model"))
        if self.sources.get(p.id) in {"keychain", "session"}:
            actions.append(("d", "remove key"))
        actions.append(("esc", "close"))
        hints = Text()
        for index, (key, label) in enumerate(actions):
            hints.append("   " if index else "")
            hints.append(key, f"bold {self.app.appearance.accent}")
            hints.append(f" {label}", QUIET)
        self.query_one("#facts-actions", Static).update(hints)

    def action_cursor(self, step: int) -> None:
        table = self.query_one(DataTable)
        table.move_cursor(row=table.cursor_row + step)

    def action_key(self) -> None:
        self.app.edit_facts_key(self, self.provider)

    def action_use(self) -> None:
        self.app.use_facts_provider(self, self.provider)

    def action_move(self, step: int) -> None:
        self.app.move_facts_provider(self, self.provider, step)

    def action_place(self, position: int) -> None:
        self.app.place_facts_provider(self, self.provider, position)

    def action_model(self) -> None:
        self.app.edit_facts_model(self, self.provider)

    def action_forget(self) -> None:
        self.app.forget_facts_key(self, self.provider)

    def action_toggle(self) -> None:
        self.app.toggle_facts(self)

    def action_close(self) -> None:
        self.dismiss(None)

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        event.stop()  # The library table's handlers live on the app.
        if 0 <= event.cursor_row < len(self.row_ids):
            self.selected_id = self.row_ids[event.cursor_row]
            self.describe()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        event.stop()


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
    FACT_DELAY = 2.0
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
        Binding("plus", "playlist_add", "Add to playlist"),
        Binding("e", "playlist_rename", "Rename playlist"),
        Binding("d", "playlist_delete", "Remove"),
        Binding("J", "playlist_move(1)", "Move down"),
        Binding("K", "playlist_move(-1)", "Move up"),
        Binding("i", "facts_setup", "Song facts"),
        Binding("left_square_bracket", "fact(-1)", "Previous fact"),
        Binding("right_square_bracket", "fact(1)", "Next fact"),
        Binding("o", "fact_source", "Open fact source"),
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
        credentials: Credentials | None = None,
        fetch_facts: Callable[[Provider, Track, str, str], list[Fact]] = request_facts,
    ):
        super().__init__()
        self.library = library
        self.playlists = Playlists(library)
        self.playlist_list: list[Playlist] = []
        self.playlist_entries: list[Entry] = []
        self.credentials = credentials or Credentials()
        self.fetch_facts_for = fetch_facts
        self.fact_cache = FactCache(library)
        self.facts_on = library.setting("facts") == "on"
        self.facts_config = FactsConfig.load(library)
        self.fact_loading_provider: Provider | None = None
        self.facts: list[Fact] = []
        self.fact_index = 0
        self.fact_path = ""
        self.fact_revision = 0
        self.facts_asked: set[tuple[str, str]] = set()  # (provider id, song) tried this session
        self.fact_loading = False
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
                with Vertical(id="fact-card"):
                    with Horizontal(id="fact-heading"):
                        yield Static("BEHIND THE RECORD", id="fact-label")
                        yield Static("✳", id="fact-spark")
                    yield Static("", id="fact-text")
                    yield TitleRhythm(id="fact-pulse")
                    yield Static("", id="fact-source")
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
        self.query_one("#fact-card").display = False
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
        await self.refresh_playlists()

    async def refresh_playlists(self) -> None:
        """Reload saved playlists, and the open playlist's entries, off the UI loop."""
        self.playlist_list = await asyncio.to_thread(self.playlists.all)
        if self.view == "playlist":
            self.playlist_entries = await asyncio.to_thread(
                self.playlists.entries, int(self.view_value)
            )
        if self.is_running:
            self.render_rows()

    def playlist(self, playlist_id: str) -> Playlist | None:
        return next((p for p in self.playlist_list if str(p.id) == playlist_id), None)

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
                else "PLAYLIST"
                if self.view == "playlists"
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
                else "SONGS"
                if self.view == "playlists"
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
            ("enter", "open" if row and row.kind in {"album", "artist", "playlist"} else "play"),
            ("space", "pause" if not (state.paused or state.idle) else "play"),
        ]
        if row and row.kind in {"track", "album", "entry", "queue"}:
            hint.append(("+", "playlist"))
        if self.view == "playlists" and row and row.kind == "playlist":
            hint += [("e", "rename"), ("d", "delete")]
        elif self.view == "playlist" and row:
            hint += [("J/K", "move"), ("d", "remove")]
        else:
            hint.append(("x", "pattern"))
        hint += [("?", "help"), ("q", "quit")]
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
                rows.extend(
                    Row("playlist", str(p.id), display_text(p.name), "Playlist")
                    for p in self.playlist_list
                    if query in p.name.casefold()
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
        elif self.view == "playlists":
            rows = [Row("new-playlist", "", "+ New playlist", "")]
            rows.extend(
                Row("playlist", str(p.id), display_text(p.name), f"{p.size}")
                for p in self.playlist_list
            )
        elif self.view == "playlist":
            playlist = self.playlist(self.view_value)
            heading = display_text(playlist.name) if playlist else "Playlist unavailable"
            for entry in self.playlist_entries if playlist else []:
                track = self.by_path.get(entry.path)
                if track:
                    row = self.track_row(track)
                    rows.append(replace(row, kind="entry", value=str(entry.id)))
                else:
                    name = display_text(Path(entry.path).name)
                    rows.append(Row("entry", str(entry.id), f"{name} [unavailable]", ""))
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
        playlist = (
            self.playlist(self.view_value)
            if self.view == "playlist" and not self.searching
            else None
        )
        breadcrumb = self.query_one("#breadcrumb", Static)
        breadcrumb.update(
            Text(f"Albums / {album.artist}" if album else "Playlists" if playlist else "")
        )
        breadcrumb.display = album is not None or playlist is not None
        if album:
            detail = (
                f"{album.tracks[0].year + ' · ' if album.tracks[0].year else ''}"
                f"{len(album.tracks)} {'song' if len(album.tracks) == 1 else 'songs'} · "
                f"{clock(sum(t.duration for t in album.tracks))}"
            )
        elif playlist:
            seconds = sum(
                self.by_path[e.path].duration
                for e in self.playlist_entries
                if e.path in self.by_path
            )
            detail = f"{len(rows)} {'song' if len(rows) == 1 else 'songs'} · {clock(seconds)}"
        elif self.view == "playlists" and not self.searching:
            detail = f"{len(self.playlist_list)} playlists"
        else:
            detail = f"{len(rows)} {'results' if self.searching else self.view}"
        self.query_one("#collection-detail", Static).update(Text(detail))
        empty = self.query_one("#empty", Static)
        empty.display = not rows
        empty.update(
            "No matching music."
            if self.searching
            else "This playlist is empty. Select a song or album elsewhere and press +."
            if self.view == "playlist"
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
            elif row.kind == "entry":
                entry = next((e for e in self.playlist_entries if str(e.id) == row.value), None)
                track = self.by_path.get(entry.path) if entry else None
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
        card = self.update_fact_card(album)
        record_note.display = bool(note.plain) and self.size.height >= 48 and not card
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
        if event.option_list.id != "nav":
            return
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
        elif row.kind == "playlist":
            self.searching = False
            self.query_one("#search").display = False
            self.open_playlist(row.value)
        elif row.kind == "new-playlist":
            self.push_screen(NameDialog("New playlist"), self.create_playlist)
        elif row.kind == "entry":
            self.play_playlist(row.value)
        self.query_one(DataTable).focus()

    @work(group="playlists")
    async def open_playlist(self, playlist_id: str) -> None:
        self.view, self.view_value = "playlist", playlist_id
        self.playlist_entries = []
        await self.refresh_playlists()
        self.query_one(DataTable).move_cursor(row=0)

    def play_playlist(self, entry_id: str) -> None:
        """Play the saved order from this entry. Missing files are skipped, not dropped."""
        playable = [
            e for e in self.playlist_entries if (t := self.by_path.get(e.path)) and t.available
        ]
        start = next((i for i, e in enumerate(playable) if str(e.id) == entry_id), None)
        if start is None:
            self.status("This file is unavailable. Restore it and rescan, or remove it with d.")
            return
        self.perform(self.player.play([e.path for e in playable], start))

    @work(group="playlists")
    async def create_playlist(self, name: str | None) -> None:
        if not name:
            return
        await asyncio.to_thread(self.playlists.create, name)
        await self.refresh_playlists()
        self.status(f"Created {display_text(name)}. Select songs or albums and press + to add.")

    def selected_paths(self) -> list[str]:
        row = self.selected()
        if not row:
            return []
        if row.kind == "track":
            return [row.value]
        if row.kind == "album" and (album := self.album(row.value)):
            return [t.path for t in album.tracks]
        if row.kind == "entry":
            return [e.path for e in self.playlist_entries if str(e.id) == row.value]
        if row.kind == "queue":
            playlist = self.player.state.playlist
            index = int(row.value)
            return [playlist[index]["filename"]] if index < len(playlist) else []
        return []

    def action_playlist_add(self) -> None:
        paths = self.selected_paths()
        if not paths:
            self.status("Select a song or album to add it to a playlist.")
            return

        def chosen(playlist_id: int | None) -> None:
            if playlist_id == 0:
                self.push_screen(
                    NameDialog("New playlist"), lambda name: self.add_to_playlist(paths, None, name)
                )
            elif playlist_id is not None:
                self.add_to_playlist(paths, playlist_id, None)

        self.push_screen(PlaylistPicker(self.playlist_list, len(paths)), chosen)

    @work(group="playlists")
    async def add_to_playlist(
        self, paths: list[str], playlist_id: int | None, name: str | None
    ) -> None:
        if playlist_id is None:
            if not name:
                return
            playlist_id = await asyncio.to_thread(self.playlists.create, name)
        await asyncio.to_thread(self.playlists.add, playlist_id, paths)
        await self.refresh_playlists()
        playlist = self.playlist(str(playlist_id))
        label = display_text(playlist.name) if playlist else "the playlist"
        self.status(f"Added {len(paths)} {'song' if len(paths) == 1 else 'songs'} to {label}.")

    def action_playlist_rename(self) -> None:
        row = self.selected()
        playlist_id = (
            row.value
            if row and row.kind == "playlist" and not self.searching
            else self.view_value
            if self.view == "playlist"
            else None
        )
        if playlist_id and (playlist := self.playlist(playlist_id)):
            self.push_screen(
                NameDialog("Rename playlist", playlist.name),
                lambda name: self.rename_playlist(playlist.id, name),
            )

    @work(group="playlists")
    async def rename_playlist(self, playlist_id: int, name: str | None) -> None:
        if name:
            await asyncio.to_thread(self.playlists.rename, playlist_id, name)
            await self.refresh_playlists()

    def action_playlist_delete(self) -> None:
        row = self.selected()
        if not row or self.searching:
            return
        if row.kind == "entry":
            self.remove_entry(int(row.value))
        elif row.kind == "playlist" and (playlist := self.playlist(row.value)):
            self.push_screen(
                ConfirmDialog(
                    f"Delete the playlist “{display_text(playlist.name)}”? "
                    "Your music files are not touched.",
                    "Delete",
                ),
                lambda confirmed: confirmed and self.delete_playlist(playlist.id),
            )

    @work(group="playlists")
    async def remove_entry(self, entry_id: int) -> None:
        await asyncio.to_thread(self.playlists.remove, entry_id)
        await self.refresh_playlists()

    @work(group="playlists")
    async def delete_playlist(self, playlist_id: int) -> None:
        await asyncio.to_thread(self.playlists.delete, playlist_id)
        await self.refresh_playlists()
        self.status("Playlist deleted. No music files were changed.")

    def action_playlist_move(self, offset: int) -> None:
        row = self.selected()
        if row and row.kind == "entry" and not self.searching:
            self.move_entry(int(row.value), offset)

    @work(group="playlists", exclusive=True)
    async def move_entry(self, entry_id: int, offset: int) -> None:
        moved = await asyncio.to_thread(self.playlists.move, int(self.view_value), entry_id, offset)
        if moved:
            await self.refresh_playlists()

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
        elif self.view == "playlist":
            ids = [str(p.id) for p in self.playlist_list]
            position = 1 + ids.index(self.view_value) if self.view_value in ids else 0
            self.view, self.view_value = "playlists", ""
            self.render_rows(position)
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
        if row and row.kind == "playlist":
            self.append_playlist(int(row.value))
        elif row and row.kind != "queue" and (paths := self.selected_paths()):
            self.append_paths(paths)

    @work(group="playlists")
    async def append_playlist(self, playlist_id: int) -> None:
        entries = await asyncio.to_thread(self.playlists.entries, playlist_id)
        paths = [e.path for e in entries if (t := self.by_path.get(e.path)) and t.available]
        if paths:
            self.append_paths(paths)
        else:
            self.status("This playlist has no available songs to append.")

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
        self.status(scan_message(progress))

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
        self.observe_fact_song(state)
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

    def observe_fact_song(self, state: PlaybackState) -> None:
        """Facts follow the playing song once it has actually started."""
        if state.loading:
            return
        path = state.path if state.path and not state.idle else ""
        if path == self.fact_path:
            return
        self.fact_path = path
        self.facts = []
        self.fact_loading = False
        self.fact_index = 0
        self.fact_revision += 1
        self.update_context()
        track = self.by_path.get(path)
        if track is None:
            return
        if self.facts_on:
            self.load_facts(track, self.fact_revision)
        elif not self.library.setting("facts"):
            self.library.set_setting("facts", "invited")
            self.status("Optional: press i for short notes on how each song was made.")

    @work(group="facts")
    async def load_facts(self, track: Track, revision: int) -> None:
        """Ask providers in order; later ones only when an earlier one fails.

        Wait out rapid skipping first. A late answer is cached but never shown for
        another song.
        """
        await asyncio.sleep(self.FACT_DELAY)
        if revision != self.fact_revision:
            return
        song = fact_key(track)
        errors: list[str] = []
        facts: list[Fact] | None = None
        for provider in self.facts_config.providers:
            facts = await asyncio.to_thread(self.fact_cache.get, provider.id, song)
            if facts is not None or revision != self.fact_revision:
                break
            if (provider.id, song) in self.facts_asked:
                continue
            api_key = await asyncio.to_thread(self.credentials.key, provider)
            if not api_key:
                continue
            self.facts_asked.add((provider.id, song))
            self.fact_loading_provider = provider
            self.fact_loading = True
            self.update_context()
            try:
                facts = await asyncio.to_thread(
                    self.fetch_facts_for,
                    provider,
                    track,
                    api_key,
                    self.facts_config.model(provider),
                )
            except FactsError as error:
                errors.append(str(error))
                continue
            finally:
                if self.is_running and revision == self.fact_revision:
                    self.fact_loading = False
                    self.update_context()
            await asyncio.to_thread(self.fact_cache.put, provider.id, song, facts)
            break
        if not self.is_running or revision != self.fact_revision:
            return
        if facts is None:
            self.status(
                " ".join(errors)
                if errors
                else "No song-notes provider with a key is in use. Press i to set one up."
            )
            return
        if errors:
            self.status(f"{' '.join(errors)} Used {facts[0].provider if facts else 'a fallback'}.")
        self.facts = facts
        self.fact_index = 0
        self.update_context()

    def update_fact_card(self, album: Album | None) -> bool:
        """Show the playing song's fact, or its title rhythm while asking for one."""
        card = self.query_one("#fact-card")
        pulse = self.query_one(TitleRhythm)
        playing = self.by_path.get(self.fact_path)
        show = (bool(self.facts) or self.fact_loading) and playing is not None
        show = show and (album is None or album.id == playing.album_id)
        loading = show and not self.facts
        if loading:
            self.query_one("#fact-text", Static).update(
                Text.assemble(
                    ("Asking ", QUIET),
                    (self.fact_loading_provider.name if self.fact_loading_provider else "", INK),
                    (" while the title keeps time", QUIET),
                )
            )
            pulse.play(
                playing.title,
                self.appearance.accent,
                self.appearance.characters == "ascii",
                self.appearance.motion == "gentle" and self.query_one("#context").display,
            )
        else:
            pulse.stop()
        pulse.display = loading
        self.query_one("#fact-source").display = show and not loading
        if show and not loading:
            fact = self.facts[self.fact_index % len(self.facts)]
            self.query_one("#fact-text", Static).update(
                Text.assemble((fact.headline, f"bold {INK}"), "\n\n", (fact.body, INK))
            )
            reading = fact.kind == "reading"
            source = Text.assemble(
                ("A reading, drawing on " if reading else "Source: ", QUIET),
                (fact.source_label, INK),
                (f" · via {fact.provider}" if fact.provider else "", QUIET),
                "\n\n",
            )
            if len(self.facts) > 1:
                source.append("[ ]", self.appearance.accent)
                source.append(f" more notes {self.fact_index + 1}/{len(self.facts)}   ", QUIET)
            source.append("o", self.appearance.accent)
            source.append(" source", QUIET)
            self.query_one("#fact-source", Static).update(source)
        if card.display != show:
            card.display = show
            self.call_after_refresh(self.query_one(RecordPane).on_resize)
        return show

    def action_fact(self, step: int) -> None:
        if len(self.facts) > 1:
            self.fact_index = (self.fact_index + step) % len(self.facts)
            self.update_context()

    def action_fact_source(self) -> None:
        if self.facts and self.query_one("#fact-card").display:
            self.open_url(self.facts[self.fact_index].source_url)

    @work(thread=True, group="browser")
    def open_url(self, url: str) -> None:
        opened = webbrowser.open(url)
        self.call_from_thread(
            self.status, "Opened the source in your browser." if opened else f"Source: {url}"
        )

    def action_facts_setup(self) -> None:
        self.push_screen(FactsSettings(), self.facts_settings_closed)

    def facts_settings_closed(self, _: None = None) -> None:
        """Apply changed providers, keys, or models to the playing song."""
        self.facts_asked.clear()  # Fixed keys and new providers deserve another try.
        self.facts = []
        self.fact_loading = False
        self.fact_path = ""
        self.observe_fact_song(getattr(self, "display_state", self.player.state))

    @work(group="facts-settings")
    async def refresh_facts_settings(self, screen: FactsSettings, note: str = "") -> None:
        sources = await asyncio.to_thread(
            lambda: {p.id: self.credentials.source(p) for p in PROVIDERS.values()}
        )
        if screen.is_mounted:
            screen.show(self.facts_config, sources, self.facts_on, note)

    @work(group="facts-settings")
    async def persist_facts(self, screen: FactsSettings, note: str = "") -> None:
        await asyncio.to_thread(self.facts_config.save, self.library)
        await asyncio.to_thread(self.library.set_setting, "facts", "on" if self.facts_on else "off")
        self.refresh_facts_settings(screen, note)

    @work(group="facts-settings")
    async def edit_facts_key(self, screen: FactsSettings, provider: Provider) -> None:
        source = await asyncio.to_thread(self.credentials.source, provider)

        def done(result: tuple[str, bool] | None) -> None:
            if result:
                self.save_facts_key(screen, provider, *result)

        self.push_screen(KeyDialog(provider, source), done)

    @work(group="facts-settings")
    async def save_facts_key(
        self, screen: FactsSettings, provider: Provider, key: str, remember: bool
    ) -> None:
        stored = await asyncio.to_thread(self.credentials.save, provider, key, remember)
        note = (
            f"{provider.name} key saved to the keychain."
            if remember and stored
            else f"{provider.name} key set for this session."
            if not remember
            else "No system keychain is available; the key lasts for this session only."
        )
        if provider.id not in self.facts_config.order:
            self.facts_config.order.append(provider.id)
            note += f" {provider.name} added to the order."
        if not self.facts_on:
            self.facts_on = True
            note += " Notes on."
        self.persist_facts(screen, note)

    def facts_role_note(self, provider: Provider) -> str:
        order = self.facts_config.order
        if provider.id not in order:
            return f"{provider.name} is no longer used."
        position = order.index(provider.id)
        return f"{provider.name} is now " + (
            "the primary." if position == 0 else f"fallback {position}."
        )

    def use_facts_provider(self, screen: FactsSettings, provider: Provider) -> None:
        order = self.facts_config.order
        if provider.id in order:
            order.remove(provider.id)
        else:
            order.append(provider.id)
        self.persist_facts(screen, self.facts_role_note(provider))

    def move_facts_provider(self, screen: FactsSettings, provider: Provider, step: int) -> None:
        order = self.facts_config.order
        if provider.id not in order:
            self.refresh_facts_settings(screen, f"Press space to use {provider.name} first.")
            return
        self.place_facts_provider(screen, provider, order.index(provider.id) + 1 + step)

    def place_facts_provider(
        self, screen: FactsSettings, provider: Provider, position: int
    ) -> None:
        """Put a provider at a 1-based position, adding it if it was not used."""
        order = self.facts_config.order
        if provider.id in order:
            order.remove(provider.id)
        order.insert(min(max(position, 1), len(order) + 1) - 1, provider.id)
        self.persist_facts(screen, self.facts_role_note(provider))

    def edit_facts_model(self, screen: FactsSettings, provider: Provider) -> None:
        if not provider.models:
            self.refresh_facts_settings(screen, f"{provider.name} chooses its own model.")
            return

        def done(model: str | None) -> None:
            if model is None:
                return
            if model and model != provider.model:
                self.facts_config.models[provider.id] = model
            else:
                self.facts_config.models.pop(provider.id, None)
            self.persist_facts(screen, f"{provider.name} uses {self.facts_config.model(provider)}.")

        self.push_screen(ModelDialog(provider, self.facts_config.model(provider)), done)

    @work(group="facts-settings")
    async def forget_facts_key(self, screen: FactsSettings, provider: Provider) -> None:
        if await asyncio.to_thread(self.credentials.source, provider) == "environment":
            note = f"{provider.environment} is set in your shell; unset it to remove that key."
        else:
            await asyncio.to_thread(self.credentials.forget, provider)
            note = f"{provider.name} key removed."
        self.refresh_facts_settings(screen, note)

    def toggle_facts(self, screen: FactsSettings) -> None:
        self.facts_on = not self.facts_on
        if not self.facts_on:
            self.fact_revision += 1  # Drop any answer still on its way.
        self.persist_facts(screen, "Notes on." if self.facts_on else "Notes off. Keys are kept.")

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
        self.query_one("#fact-spark", Static).update(
            "*" if self.appearance.characters == "ascii" else "✳"
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
            "+ add to playlist · in a playlist: J/K move · d remove · e rename\n"
            "i song facts setup · [ ] more facts · o open the fact's source\n"
            "Typing in search, name, or key fields never triggers playback shortcuts.",
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
