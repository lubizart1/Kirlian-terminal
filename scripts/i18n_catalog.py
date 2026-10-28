# SPDX-License-Identifier: GPL-3.0-or-later
"""Collect translatable strings and check the language catalogs against them.

uv run python scripts/i18n_catalog.py            # report gaps for every language
uv run python scripts/i18n_catalog.py --template # write locales/_template.json

The template lists each English source with where it is used and, for plurals,
the English plural form. Translators copy it to `<code>.json` and fill in values.
"""

from __future__ import annotations

import argparse
import ast
import json
import string
import sys
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1] / "src" / "kirlian_terminal"
LOCALES = PACKAGE / "locales"


def extract(package: Path = PACKAGE) -> dict[str, dict]:
    """English source -> {"plural": str | None, "where": [file:line, ...]}."""
    found: dict[str, dict] = {}
    for path in sorted(package.glob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            name = getattr(node, "func", None) and getattr(node.func, "id", "")
            if not isinstance(node, ast.Call) or name not in {"_", "n_", "N_"}:
                continue
            args = node.args
            if (
                not args
                or not isinstance(args[0], ast.Constant)
                or not isinstance(args[0].value, str)
            ):
                raise ValueError(f"{path.name}:{node.lineno}: first argument must be a literal")
            plural = None
            if node.func.id == "n_":
                if len(args) < 2 or not isinstance(args[1], ast.Constant):
                    raise ValueError(f"{path.name}:{node.lineno}: n_ needs a literal plural")
                plural = args[1].value
            entry = found.setdefault(args[0].value, {"plural": plural, "where": []})
            entry["where"].append(f"{path.name}:{node.lineno}")
    return found


def fields(text: str) -> set[str]:
    return {name for _, name, _, _ in string.Formatter().parse(text) if name is not None}


def problems(code: str, sources: dict[str, dict] | None = None) -> list[str]:
    """Missing or stale entries, wrong shapes, and placeholder mismatches."""
    sources = extract() if sources is None else sources
    try:
        catalog = json.loads((LOCALES / f"{code}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        return [f"{code}: unreadable catalog ({error})"]
    found = []
    for source, info in sources.items():
        value = catalog.get(source)
        expected = fields(source) | (fields(info["plural"]) if info["plural"] else set())
        if info["plural"]:
            if not isinstance(value, dict) or not {"one", "other"} <= value.keys():
                found.append(f"{code}: plural needs one/other: {source!r}")
                continue
            texts = [value["one"], value["other"]]
        else:
            if not isinstance(value, str) or not value:
                found.append(f"{code}: missing {source!r}")
                continue
            texts = [value]
        for text in texts:
            try:
                names = fields(text)
            except ValueError:
                found.append(f"{code}: broken braces in {text!r}")
                continue
            # Plural "one" forms may omit {n}; nothing may invent a new placeholder.
            if not names <= expected or (expected - {"n"}) - names:
                wanted = sorted(expected)
                found.append(f"{code}: placeholders {sorted(names)} != {wanted}: {source!r}")
    found += [f"{code}: stale {key!r}" for key in catalog if key not in sources]
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--template", action="store_true", help="Write locales/_template.json")
    args = parser.parse_args()
    sources = extract()
    if args.template:
        LOCALES.mkdir(exist_ok=True)
        (LOCALES / "_template.json").write_text(
            json.dumps(sources, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"{len(sources)} strings written to {LOCALES / '_template.json'}")
        return 0
    sys.path.insert(0, str(PACKAGE.parent))
    from kirlian_terminal.i18n import LANGUAGES

    failures = [p for code in LANGUAGES if code != "en" for p in problems(code, sources)]
    print("\n".join(failures) or f"All catalogs cover {len(sources)} strings.")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
