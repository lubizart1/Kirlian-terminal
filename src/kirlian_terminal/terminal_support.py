# SPDX-License-Identifier: GPL-3.0-or-later
"""Bounded terminal identity checks, before Textual takes ownership of input."""

import os
import re
import select
import sys
import time
from functools import cache


def read_replies(fd: int, timeout: float = 2.0) -> str:
    """Read until the final DA reply, with a total deadline and byte limit."""
    deadline = time.monotonic() + timeout
    data = bytearray()
    while len(data) < 8192:
        remaining = deadline - time.monotonic()
        if remaining <= 0 or not select.select([fd], [], [], remaining)[0]:
            break
        chunk = os.read(fd, 8192 - len(data))
        if not chunk:
            break
        data.extend(chunk)
        if re.search(rb"\x1b\[\?[0-9;]*c", data):
            break
    return data.decode("utf-8", errors="replace")


def safe_text(value: str) -> str:
    return "".join(c for c in value if c.isascii() and c.isprintable())[:100]


def terminal_version(replies: str) -> str:
    match = re.search(r"\x1bP>\|([^\x1b]*)\x1b\\", replies)
    return safe_text(match[1]) if match else "no reply"


@cache
def query_terminal_version() -> str:
    """Identify the responder, rather than trusting inherited TERM_PROGRAM.

    A reply identifies an implementation; it does not certify image visibility.
    Call only at startup, before the app starts its input reader.
    """
    stdin, stdout = sys.__stdin__, sys.__stdout__
    if not stdin or not stdout or not stdin.isatty() or not stdout.isatty():
        return "no reply"

    from textual_image._terminal import TerminalError, capture_mode, prepare_terminal_sequence

    try:
        with capture_mode():
            stdout.write(prepare_terminal_sequence("\x1b[>q"))
            stdout.write(prepare_terminal_sequence("\x1b[c"))
            stdout.flush()
            return terminal_version(read_replies(stdin.fileno(), timeout=0.5))
    except (OSError, ValueError, TerminalError):
        return "no reply"
