"""A byte-level tmux envelope model; not a terminal renderer."""

import re


def unwrap_tmux(data: bytes) -> bytes:
    stream = re.sub(
        rb"\x1bPtmux;((?:[^\x1b]|\x1b\x1b)*)\x1b\\",
        lambda match: match[1].replace(b"\x1b\x1b", b"\x1b"),
        data,
    )
    # Keep plain queries (tmux itself answers DA), but wait for completion of
    # any partial envelope before parsing its contents or later bytes.
    return stream.split(b"\x1bPtmux;", 1)[0]
