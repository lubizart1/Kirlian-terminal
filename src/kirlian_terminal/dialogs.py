# SPDX-License-Identifier: GPL-3.0-or-later
"""Modal screens: folder, names, playlist choice, confirmation, and song-notes settings."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Input, Label, OptionList, Static

from . import i18n, picker
from .appearance import INK, QUIET
from .facts import (
    PROVIDERS,
    FactsConfig,
    Provider,
)
from .i18n import _, n_
from .library import display_text
from .playlists import Playlist
from .stores import STORES


class FolderDialog(ModalScreen[str | None]):
    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def compose(self) -> ComposeResult:
        with Vertical(id="folder-dialog"):
            yield Label(_("Kirlian · Your music, locally"))
            yield Static(_("Choose a folder to begin. Make it yours later with p."))
            yield Static(
                _("Your files and tags stay untouched. Indexing happens in the background.")
            )
            yield Input(placeholder="~/Music", id="folder-path")
            yield Static("", id="folder-error")
            with Horizontal(id="folder-actions"):
                yield Button(_("Open folder"), variant="primary", id="folder-open")
                if picker.command(""):
                    label = _("Choose in Finder…") if sys.platform == "darwin" else _("Browse…")
                    yield Button(label, id="folder-browse")

    def on_mount(self) -> None:
        self.query_one(Input).focus()

    def on_input_submitted(self) -> None:
        self.submit()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "folder-browse":
            self.browse()
        else:
            self.submit()

    @work(exclusive=True, group="folder-picker")
    async def browse(self) -> None:
        try:
            chosen = await picker.choose(_("Choose your music folder"))
        except picker.PickerError:
            error = _("Could not open the folder picker. Type the path instead.")
            self.query_one("#folder-error", Static).update(error)
            return
        if chosen and self.is_mounted:
            self.query_one(Input).value = chosen
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
            self.query_one("#folder-error", Static).update(_("Enter an existing, readable folder."))
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
            yield Input(value=self.value, placeholder=_("Playlist name"), id="playlist-name")
            yield Static(_("Enter saves · Esc cancels"), classes="dialog-hint")

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
            yield Label(n_("Add {n} song to…", "Add {n} songs to…", self.count))
            yield OptionList(
                _("+ New playlist…"),
                *(Text(display_text(p.name)) for p in self.playlists),
                id="playlist-choices",
            )
            yield Static(_("Enter chooses · Esc cancels"), classes="dialog-hint")

    def on_mount(self) -> None:
        self.query_one(OptionList).focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        index = event.option_index
        self.dismiss(self.playlists[index - 1].id if index else 0)

    def action_cancel(self) -> None:
        self.dismiss(None)


class StorePicker(ModalScreen[str | None]):
    """Returns a store id from stores.STORES."""

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, album: str) -> None:
        super().__init__()
        self.album = album

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog"):
            yield Label(_("Stream or buy {album}", album=display_text(self.album)))
            yield OptionList(*(name for _sid, name, _url in STORES), id="store-choices")
            yield Static(
                _("Opens the store's search in your browser. Enter chooses · Esc cancels"),
                classes="dialog-hint",
            )

    def on_mount(self) -> None:
        self.query_one(OptionList).focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        self.dismiss(STORES[event.option_index][0])

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
                yield Button(_("Cancel"), id="cancel")

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
            yield Label(_("{provider} API key", provider=p.name))
            note = {
                "environment": _(
                    "{variable} is set in your environment and takes precedence; a key saved "
                    "here is used once it is unset.",
                    variable=p.environment,
                ),
                "keychain": _("Replacing the saved key. The old one is overwritten."),
                "session": _("Replacing this session's key."),
            }.get(
                self.source,
                _(
                    "Create one at {signup}. {provider} bills your account.",
                    signup=p.signup,
                    provider=p.name,
                ),
            )
            yield Static(note, classes="dialog-hint")
            yield Input(
                password=True, placeholder=_("{provider} API key", provider=p.name), id="facts-key"
            )
            yield Static("", id="facts-error")
            with Horizontal(classes="dialog-buttons"):
                yield Button(_("Save to keychain"), id="keep", variant="primary")
                yield Button(_("This session only"), id="session")
                yield Button(_("Cancel"), id="cancel")

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
            self.query_one("#facts-error", Static).update(_("Paste a key, or press Esc."))
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
            yield Label(_("Which {provider} model writes your notes?", provider=p.name))
            yield Static(
                _(
                    "{provider} searches the web, then this model reads the pages and writes "
                    "the notes. Larger models usually find better stories and readings, take "
                    "longer, and cost more per song. This changes song notes only.",
                    provider=p.name,
                ),
                classes="dialog-hint",
            )
            options = [
                Text.assemble(
                    ("● " if model == self.current else "  ", self.app.appearance.accent),
                    (model, f"bold {INK}"),
                    ("  " + _("default") if model == p.model else "", QUIET),
                    "\n    " + i18n._(about),
                )
                for model, about in p.models
            ]
            options.append(
                Text("  " + _("Another model…") + "\n    " + _("Type any model name it offers"))
            )
            yield OptionList(*options, id="model-choices")
            yield Input(placeholder=_("{provider} model name", provider=p.name), id="facts-model")

    def on_mount(self) -> None:
        choices = self.query_one(OptionList)
        names = [model for model, _about in self.provider.models]
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
        Binding("a", "albums", "Album notes on/off"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.row_ids: list[str] = list(PROVIDERS)
        self.selected_id = self.row_ids[0]
        self.config = FactsConfig()
        self.sources: dict[str, str] = {}

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog", id="facts-settings"):
            yield Label(_("Song notes · Behind the record"))
            yield Static("", id="facts-state")
            yield Static(
                _(
                    "Providers are asked from the top. The primary answers every new song; a "
                    "fallback is asked only if the ones above it fail. Sent: title, artist, "
                    "album, year, language. Never: audio, artwork, or file paths."
                ),
                classes="dialog-hint",
            )
            yield DataTable(id="facts-providers", cursor_type="row", zebra_stripes=False)
            yield Static("", id="facts-detail")
            yield Static("", id="facts-actions")
            yield Static("", id="facts-note")

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        for label in (_("Role"), _("Provider"), _("Key"), _("Writes notes with")):
            table.add_column(label)
        self.app.refresh_facts_settings(self)
        table.focus()

    @property
    def provider(self) -> Provider:
        return PROVIDERS[self.selected_id]

    def role(self, provider_id: str) -> str:
        order = self.config.order
        if provider_id not in order:
            return _("Not used")
        position = order.index(provider_id)
        return _("Primary") if position == 0 else _("Fallback {position}", position=position)

    def key_label(self, p: Provider) -> str:
        return {
            "keychain": _("Saved in keychain"),
            "session": _("This session only"),
            "environment": _("From shell ({variable})", variable=p.environment),
        }.get(self.sources.get(p.id, ""), _("No key"))

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
                Text(config.model(p) or _("its own model"), INK if config.model(p) else QUIET),
                key=provider_id,
            )
        table.move_cursor(row=self.row_ids.index(self.selected_id))
        self.query_one("#facts-state", Static).update(
            Text.assemble(
                (
                    _("Notes are on") if on else _("Notes are off"),
                    f"bold {accent}" if on else "bold",
                ),
                ("  ·  ", QUIET),
                ("t", "bold"),
                (" " + (_("to turn off") if on else _("to turn on")), QUIET),
                ("     ", ""),
                (
                    _("Album notes too") if config.albums else _("No album notes"),
                    f"bold {accent}" if on and config.albums else "bold",
                ),
                ("  ·  ", QUIET),
                ("a", "bold"),
                (" " + (_("to turn off") if config.albums else _("to turn on")), QUIET),
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
            role = _("Not used. Press space to add it as the last fallback.")
        elif order.index(p.id) == 0:
            role = _("Primary: asked first for every new song.")
        else:
            above = PROVIDERS[order[order.index(p.id) - 1]].name
            role = _("Fallback: asked only if {provider} fails.", provider=above)
        writer = (
            _("Notes are written by {model}.", model=model)
            if model
            else _("{provider} picks the model that writes the notes.", provider=p.name)
        )
        self.query_one("#facts-detail", Static).update(
            Text.assemble((p.name, f"bold {INK}"), "  ", (f"{role} {writer}", QUIET))
        )
        actions = [("enter", _("replace key") if self.sources.get(p.id) else _("add key"))]
        if p.id in order:
            actions.append(("space", _("stop using")))
            if len(order) > 1:
                actions.append(("K/J or 1-5", _("move up/down")))
        else:
            actions.append(("space", _("use as fallback")))
            actions.append(("1", _("make primary")))
        if p.models:
            actions.append(("m", _("change model")))
        if self.sources.get(p.id) in {"keychain", "session"}:
            actions.append(("d", _("remove key")))
        actions.append(("esc", _("close")))
        hints = Text()
        for index, (key, label) in enumerate(actions):
            hints.append("   " if index else "")
            hints.append(key, f"bold {self.app.appearance.accent}")
            hints.append(f" {label}", QUIET)
        self.query_one("#facts-actions", Static).update(hints)

    def action_cursor(self, step: int) -> None:
        table = self.query_one(DataTable)
        table.move_cursor(row=table.cursor_row + step)

    def action_albums(self) -> None:
        self.app.toggle_album_notes(self)

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
