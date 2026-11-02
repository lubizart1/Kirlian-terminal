# SPDX-License-Identifier: GPL-3.0-or-later
"""Command-line entry point with readable prerequisite failures."""

import argparse
import logging
import re
import shutil
import sqlite3
import sys
from pathlib import Path

from platformdirs import user_data_path

from . import __version__
from .library import Library


def main() -> None:
    parser = argparse.ArgumentParser(description="Kirlian Terminal — local, album-first listening")
    parser.add_argument(
        "--version",
        action="version",
        version=f"kirlian-terminal {__version__}\nLicense: GPL-3.0-or-later. "
        "This is free software; there is NO WARRANTY.",
    )
    parser.add_argument("--music", type=Path, help="Music folder to index on launch")
    parser.add_argument("--data-dir", type=Path, help="Override application data directory")
    parser.add_argument(
        "--artwork",
        choices=("auto", "native", "blocks", "off"),
        help="Cover display: auto, terminal graphics, or compatible colored blocks, or off",
    )
    parser.add_argument("--characters", choices=("dots", "ascii"), help="Ribbon character override")
    parser.add_argument(
        "--new-theme",
        metavar="NAME",
        help="Create a theme file to edit; it then appears under Interface palette in p",
    )
    parser.add_argument(
        "--check-artwork",
        action="store_true",
        help="Compare native images and block artwork without opening the music library",
    )
    parser.add_argument(
        "--artwork-report",
        type=Path,
        help="Save --check-artwork results as local JSON at this path",
    )
    facts = parser.add_argument_group("song facts check")
    facts.add_argument(
        "--check-facts",
        nargs="?",
        const="",
        metavar="PROVIDER",
        help="Make one live song-notes request and show what passes the source check. "
        "PROVIDER is exa, openai, anthropic, perplexity, parallel, or all (keys found); "
        "default: your primary provider",
    )
    facts.add_argument("--artist", default="John Cale", help="Artist for --check-facts")
    facts.add_argument("--title", default="Paris 1919", help="Song title for --check-facts")
    facts.add_argument("--album", default="Paris 1919", help="Album for --check-facts")
    facts.add_argument("--year", default="1973", help="Year for --check-facts")
    facts.add_argument(
        "--model", default="", help="Model for --check-facts (OpenAI and Anthropic only)"
    )
    facts.add_argument(
        "--facts-report", type=Path, help="Save --check-facts responses as local JSON"
    )
    args = parser.parse_args()
    if args.artwork_report and not args.check_artwork:
        parser.error("--artwork-report requires --check-artwork")
    if args.facts_report and args.check_facts is None:
        parser.error("--facts-report requires --check-facts")
    if args.check_artwork:
        from .artwork_check import run_artwork_check

        run_artwork_check(args.artwork_report)
        return
    data = args.data_dir or user_data_path("kirlian-terminal", appauthor=False)
    if args.new_theme is not None:
        raise SystemExit(new_theme(args.new_theme, data.expanduser() / "themes"))
    if args.check_facts is not None:
        from .facts import FactsConfig
        from .facts_check import run_facts_check

        config = FactsConfig()
        database = data.expanduser() / "library.sqlite3"
        if database.exists():
            config = FactsConfig.load(Library(database))
        song = (args.artist, args.title, args.album, args.year)
        raise SystemExit(
            run_facts_check(
                args.check_facts or None, config, song, args.facts_report, model=args.model
            )
        )
    if not shutil.which("mpv"):
        print(
            "Kirlian needs mpv for audio playback.\n"
            "macOS (Homebrew): brew install mpv\n"
            "Debian/Ubuntu: sudo apt install mpv\n"
            "Other Linux distributions: install mpv with your package manager.\n"
            "Then run kirlian again.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    try:
        library = Library(data.expanduser() / "library.sqlite3")
    except (OSError, sqlite3.Error) as error:
        print(
            f"Kirlian could not open its library: {error}\n"
            "Try --data-dir with a writable directory.",
            file=sys.stderr,
        )
        raise SystemExit(1) from error
    # Unsupported graphics queries are normal: silently use the image fallback.
    logging.getLogger("textual_image._terminal").setLevel(logging.ERROR)
    # Import only after argument parsing: graphics detection owns terminal input.
    from .app import KirlianApp

    KirlianApp(library, folder=args.music, artwork=args.artwork, characters=args.characters).run()


def new_theme(name: str, folder: Path) -> int:
    from .appearance import PALETTES, display_name, theme_template

    label = display_name(name)
    stem = re.sub(r"[^a-z0-9]+", "-", label.casefold()).strip("-") or "theme"
    path = folder / f"{stem}.toml"
    if path.exists():
        print(f"{path} already exists; edit it, or choose another name.", file=sys.stderr)
        return 1
    try:
        folder.mkdir(parents=True, exist_ok=True)
        path.write_text(theme_template(label, PALETTES["aubergine"]), encoding="utf-8")
    except OSError as error:
        print(f"Could not write {path}: {error}", file=sys.stderr)
        return 1
    print(
        f"Created {path}\n"
        "Edit the colors, then open Kirlian and press p: it is listed under Interface "
        'palette as "' + label + '". Reopening p rereads the file, so you can keep editing.'
    )
    return 0


if __name__ == "__main__":
    main()
