# SPDX-License-Identifier: GPL-3.0-or-later
"""The system folder picker: Finder on macOS, zenity or kdialog on a Linux desktop."""

from __future__ import annotations

import asyncio
import os
import shutil
import sys
from pathlib import Path

# The prompt arrives as an argument, never inside the script, so no text can change it.
MACOS_SCRIPT = (
    "on run argv",
    "POSIX path of (choose folder with prompt (item 1 of argv))",
    "end run",
)


def command(prompt: str) -> list[str] | None:
    """How to ask for a folder here, or None when no picker can be shown (e.g. over SSH)."""
    if sys.platform == "darwin":
        if os.environ.get("SSH_CONNECTION") or not shutil.which("osascript"):
            return None
        script = [part for line in MACOS_SCRIPT for part in ("-e", line)]
        return ["osascript", *script, prompt]
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        return None
    if zenity := shutil.which("zenity"):
        return [zenity, "--file-selection", "--directory", f"--title={prompt}"]
    if kdialog := shutil.which("kdialog"):
        return [kdialog, "--getexistingdirectory", str(Path.home()), "--title", prompt]
    return None


class PickerError(Exception):
    """The picker could not be shown; typing the path still works."""


async def choose(prompt: str) -> str | None:
    """The chosen folder, or None if the listener cancelled."""
    argv = command(prompt)
    if argv is None:
        raise PickerError
    try:
        process = await asyncio.create_subprocess_exec(
            *argv,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
    except OSError as error:
        raise PickerError from error
    try:
        output, _ = await process.communicate()
    except asyncio.CancelledError:
        process.kill()  # The dialog was closed in the terminal; close the picker too.
        raise
    chosen = output.decode("utf-8", "replace").strip()
    # A cancelled picker exits non-zero (Finder: error -128) with no output.
    return chosen if process.returncode == 0 and chosen else None
