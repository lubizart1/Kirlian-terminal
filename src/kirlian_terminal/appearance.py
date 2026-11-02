# SPDX-License-Identifier: GPL-3.0-or-later
"""Local appearance preferences and the small, curated color set."""

from __future__ import annotations

import json
import os
import re
import tomllib
from dataclasses import asdict, dataclass
from pathlib import Path

from textual.theme import Theme

from .i18n import LANGUAGES, N_
from .library import Library


@dataclass
class Colors:
    """Every color the interface draws with. A palette or a theme file sets these."""

    accent: str = "#c69bb9"
    selection: str = "#493247"  # The highlighted row.
    text: str = "#e8e1d1"
    muted: str = "#a29a9f"  # Labels, hints, secondary text.
    faint: str = "#4f4752"  # Empty meter cells, the unplayed progress line.
    edge: str = "#363139"  # Borders and dividers.
    background: str = "#121114"
    panel: str = "#1c1920"  # Fields and dropdowns.
    dialog: str = "#19161c"  # Dialogs and lists inside them.
    warning: str = "#e2a895"  # CLIP, errors, loud meter cells.


# The built-in palettes; custom themes are added by load_themes.
PALETTES: dict[str, Colors] = {
    "aubergine": Colors(),
    "sage": Colors(accent="#afc7b3", selection="#33493a"),
    "amber": Colors(accent="#d9b583", selection="#4a3927"),
}
# The palette in use. Widgets read it while drawing, so a switch recolors everything.
COLORS = Colors()


THEME_KEYS = tuple(vars(Colors()))
HEX = re.compile(r"#[0-9a-fA-F]{6}")


def load_themes(folder: Path) -> list[str]:
    """Add each `*.toml` theme in `folder` as a palette; return problems, one per file.

    Reloading replaces earlier custom themes, so an edited file shows its new colors.
    """
    for name in [name for name in PALETTES if name.startswith("custom-")]:
        del PALETTES[name]
    OPTIONS["palette"][:] = [o for o in OPTIONS["palette"] if not o[1].startswith("custom-")]
    problems = []
    for path in sorted(folder.glob("*.toml")) if folder.is_dir() else ():
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, tomllib.TOMLDecodeError) as error:
            problems.append(f"{path.name}: {error}")
            continue
        label = str(data.pop("name", "") or path.stem)[:40]
        unknown = sorted(set(data) - set(THEME_KEYS))
        bad = sorted(k for k in THEME_KEYS if k in data and not HEX.fullmatch(str(data[k])))
        if unknown or bad:
            reason = ", ".join(
                ([f"unknown {', '.join(unknown)}"] if unknown else [])
                + ([f"not a #rrggbb color: {', '.join(bad)}"] if bad else [])
            )
            problems.append(f"{path.name}: {reason}")
            continue
        slug = re.sub(r"[^a-z0-9]+", "-", path.stem.casefold()).strip("-") or "theme"
        PALETTES[f"custom-{slug}"] = Colors(**{key: str(value) for key, value in data.items()})
        OPTIONS["palette"].append((display_name(label), f"custom-{slug}"))
    return problems


def display_name(label: str) -> str:
    return "".join(c if c.isprintable() else " " for c in label).strip() or "Theme"


def theme_template(name: str, base: Colors) -> str:
    """A theme file to edit: every color, commented, starting from `base`."""
    notes = {
        "accent": "keys, highlights, the playhead",
        "selection": "the highlighted row",
        "text": "titles and body text",
        "muted": "labels and hints",
        "faint": "empty meter cells, the unplayed progress line",
        "edge": "borders and dividers",
        "background": "the window",
        "panel": "text fields and dropdowns",
        "dialog": "dialogs",
        "warning": "CLIP, errors, loud meter cells",
    }
    lines = [
        "# A Kirlian Terminal theme. Colors are #rrggbb; remove a line to keep the default.",
        "# Save, then open p (personalize) to preview it; the list rereads this folder.",
        f"name = {json.dumps(name, ensure_ascii=False)}",  # Quotes escaped: valid TOML.
        "",
    ]
    lines += [f'{key} = "{getattr(base, key)}"  # {notes[key]}' for key in THEME_KEYS]
    return "\n".join(lines) + "\n"


def use_palette(name: str) -> None:
    for key, value in vars(PALETTES[name]).items():
        setattr(COLORS, key, value)


OPTIONS = {
    "palette": [(N_("Aubergine"), "aubergine"), (N_("Sage"), "sage"), (N_("Amber"), "amber")],
    "motion": [(N_("Gentle"), "gentle"), (N_("Still"), "still"), (N_("Off"), "off")],
    "characters": [(N_("Fine dots"), "dots"), (N_("Plain ASCII"), "ascii")],
    "amp": [(N_("In the playbar"), "playback"), (N_("Under the cover"), "record")],
    "language": [
        (N_("System language"), "auto"),
        *((name, code) for code, (name, _) in LANGUAGES.items()),
    ],
}


@dataclass(frozen=True)
class Appearance:
    palette: str = "aubergine"
    motion: str = "gentle"
    characters: str = "dots"
    language: str = "auto"
    amp: str = "playback"  # Where the amp shows when open (w).

    @property
    def accent(self) -> str:
        return PALETTES[self.palette].accent

    @classmethod
    def load(cls, library: Library) -> Appearance:
        try:
            stored = json.loads(library.setting("appearance") or "{}")
            if not isinstance(stored, dict):
                stored = {}
        except (TypeError, ValueError):
            stored = {}
        if "motion" not in stored and library.setting("animations_enabled") == "false":
            stored["motion"] = "off"
        if "characters" not in stored and os.environ.get("TERM") in {"linux", "dumb"}:
            stored["characters"] = "ascii"
        return cls(
            **{
                name: value
                for name, value in stored.items()
                if name in OPTIONS and value in [option[1] for option in OPTIONS[name]]
            }
        )

    def save(self, library: Library) -> None:
        library.set_setting("appearance", json.dumps(asdict(self)))


def themes() -> list[Theme]:
    return [
        Theme(
            name=f"kirlian-{name}",
            primary=colors.accent,
            accent=colors.accent,
            foreground=colors.text,
            background=colors.background,
            surface=colors.background,
            panel=colors.panel,
            dark=True,
            variables={
                "k-accent": colors.accent,
                "k-selected": colors.selection,
                "k-ink": colors.text,
                "k-quiet": colors.muted,
                "k-surface": colors.background,
                "k-edge": colors.edge,
                "k-field": colors.panel,
                "k-dialog": colors.dialog,
                "k-warning": colors.warning,
            },
        )
        for name, colors in PALETTES.items()
    ]
