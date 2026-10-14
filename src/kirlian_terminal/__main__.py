"""Command-line entry point with readable prerequisite failures."""

import argparse
import logging
import shutil
import sqlite3
import sys
from pathlib import Path

from platformdirs import user_data_path

from . import __version__
from .library import Library


def main() -> None:
    parser = argparse.ArgumentParser(description="Kirlian Terminal — local, album-first listening")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--music", type=Path, help="Music folder to index on launch")
    parser.add_argument("--data-dir", type=Path, help="Override application data directory")
    parser.add_argument(
        "--artwork",
        choices=("auto", "native", "blocks", "off"),
        help="Cover display: auto, terminal graphics, or compatible colored blocks, or off",
    )
    parser.add_argument("--characters", choices=("dots", "ascii"), help="Ribbon character override")
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
    args = parser.parse_args()
    if args.artwork_report and not args.check_artwork:
        parser.error("--artwork-report requires --check-artwork")
    if args.check_artwork:
        from .artwork_check import run_artwork_check

        run_artwork_check(args.artwork_report)
        return
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
    data = args.data_dir or user_data_path("kirlian-terminal", appauthor=False)
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


if __name__ == "__main__":
    main()
