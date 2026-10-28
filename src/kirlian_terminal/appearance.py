# SPDX-License-Identifier: GPL-3.0-or-later
"""Local appearance preferences and the small, curated color set."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass

from textual.theme import Theme

from .library import Library

INK = "#e8e1d1"
QUIET = "#a29a9f"
SURFACE = "#121114"
PALETTES = {
    "aubergine": ("#c69bb9", "#493247"),
    "sage": ("#afc7b3", "#33493a"),
    "amber": ("#d9b583", "#4a3927"),
}
OPTIONS = {
    "palette": [("Aubergine", "aubergine"), ("Sage", "sage"), ("Amber", "amber")],
    "motion": [("Gentle", "gentle"), ("Still", "still"), ("Off", "off")],
    "characters": [("Fine dots", "dots"), ("Plain ASCII", "ascii")],
    "logo": [("Drawn wordmark", "auto"), ("Simple wordmark", "text")],
}


@dataclass(frozen=True)
class Appearance:
    palette: str = "aubergine"
    motion: str = "gentle"
    characters: str = "dots"
    logo: str = "auto"

    @property
    def accent(self) -> str:
        return PALETTES[self.palette][0]

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
            primary=accent,
            accent=accent,
            foreground=INK,
            background=SURFACE,
            surface=SURFACE,
            panel="#1c1920",
            dark=True,
            variables={
                "k-accent": accent,
                "k-selected": selected,
                "k-ink": INK,
                "k-quiet": QUIET,
                "k-surface": SURFACE,
                "k-edge": "#363139",
            },
        )
        for name, (accent, selected) in PALETTES.items()
    ]
