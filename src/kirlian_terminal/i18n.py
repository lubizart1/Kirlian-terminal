# SPDX-License-Identifier: GPL-3.0-or-later
"""Interface language: English source strings looked up in small JSON catalogs.

Code marks visible text with `_("English text", name=value)` or, when a count
changes the wording, `n_("{n} song", "{n} songs", n)`. Catalogs live in
`locales/<code>.json` and map each English source string to its translation; a
plural entry maps the singular source to {"one": ..., "other": ...}. Anything
missing falls back to English, so a gap shows English rather than breaking.
Values are inserted with `str.format`, so literal braces in sources are doubled.
Tags, filenames, and provider text are never passed through these functions.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path

LOCALES = Path(__file__).with_name("locales")

# Code: (name in that language, name in English for prompts and docs).
LANGUAGES: dict[str, tuple[str, str]] = {
    "en": ("English", "English"),
    "es": ("Español", "Spanish"),
    "fr": ("Français", "French"),
    "de": ("Deutsch", "German"),
    "it": ("Italiano", "Italian"),
    "pt-BR": ("Português (Brasil)", "Brazilian Portuguese"),
    "ja": ("日本語", "Japanese"),
    "ko": ("한국어", "Korean"),
    "zh-Hans": ("简体中文", "Simplified Chinese"),
}
DEFAULT = "en"

_catalog: dict[str, object] = {}
_language = DEFAULT


def system_language(environ: Mapping[str, str] = os.environ) -> str:
    """The first supported language named by LC_ALL, LC_MESSAGES, or LANG."""
    for name in ("LC_ALL", "LC_MESSAGES", "LANG"):
        value = environ.get(name, "")
        if not value:
            continue
        tag = value.split(".")[0].split("@")[0].replace("_", "-")
        language, _, region = tag.partition("-")
        language, region = language.casefold(), region.upper()
        if language in {"c", "posix"}:
            return DEFAULT
        if language == "zh":
            # Only Simplified Chinese is translated; Traditional regions get English.
            return "zh-Hans" if region in {"", "CN", "SG", "HANS"} else DEFAULT
        if language == "pt":
            return "pt-BR"
        return language if language in LANGUAGES else DEFAULT
    return DEFAULT


def resolve(setting: str | None, environ: Mapping[str, str] = os.environ) -> str:
    """A saved choice wins; "auto" or nothing follows the system locale."""
    return setting if setting in LANGUAGES else system_language(environ)


def load(code: str) -> dict[str, object]:
    if code == DEFAULT:
        return {}
    try:
        catalog = json.loads((LOCALES / f"{code}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return catalog if isinstance(catalog, dict) else {}


def set_language(code: str) -> None:
    global _catalog, _language
    _language = code if code in LANGUAGES else DEFAULT
    _catalog = load(_language)


def language() -> str:
    return _language


def english_name(code: str | None = None) -> str:
    return LANGUAGES[code or _language][1]


def _(text: str, /, **values: object) -> str:
    translated = _catalog.get(text)
    result = translated if isinstance(translated, str) and translated else text
    return result.format(**values) if values else result


def N_(text: str, /) -> str:
    """Mark text for translation where it is defined; translate it later with `_`."""
    return text


def plural_form(count: int, code: str) -> str:
    if code in {"ja", "ko", "zh-Hans"}:
        return "other"
    if code in {"fr", "pt-BR"}:
        return "one" if count in (0, 1) else "other"
    return "one" if count == 1 else "other"


def n_(singular: str, plural: str, count: int, /, **values: object) -> str:
    """Count-dependent text; `n` is always available to the format string."""
    entry = _catalog.get(singular)
    form = plural_form(count, _language)
    if isinstance(entry, dict) and isinstance(entry.get(form), str) and entry[form]:
        text = entry[form]
    else:
        text = singular if count == 1 else plural
    return text.format(n=count, **values)
