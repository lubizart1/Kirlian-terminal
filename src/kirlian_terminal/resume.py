# SPDX-License-Identifier: GPL-3.0-or-later
"""Where the listener was: the queue, the song in it, and the position in that song."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass

from .library import Library
from .playback import PlaybackState

KEY = "resume"
# Saving every position update would write several times a second; this is enough
# to come back within a few seconds of where listening stopped, even after a crash.
STEP = 5.0


@dataclass(frozen=True)
class Place:
    paths: tuple[str, ...]
    index: int = 0
    position: float = 0.0

    @classmethod
    def of(cls, state: PlaybackState) -> Place | None:
        """The place mpv reports, or None when the queue is empty."""
        paths = tuple(str(item.get("filename", "")) for item in state.playlist)
        if not paths or not all(paths):
            return None
        if state.idle or not 0 <= state.index < len(paths):
            return cls(paths)  # Finished or stopped: keep the queue, start from its top.
        return cls(paths, state.index, round(max(0.0, state.position), 1))

    def moved_from(self, other: Place | None) -> bool:
        """Worth saving: another queue or song, or a few seconds further along."""
        if other is None or (self.paths, self.index) != (other.paths, other.index):
            return True
        return abs(self.position - other.position) >= STEP

    @classmethod
    def load(cls, library: Library) -> Place | None:
        """The saved place, without songs whose files have gone; None if nothing is left."""
        try:
            data = json.loads(library.setting(KEY) or "null")
            paths = [str(path) for path in data["paths"]]
            index, position = int(data["index"]), float(data["position"])
        except (TypeError, KeyError, ValueError):
            return None
        # Keep each entry's original position: a queue may hold the same song twice.
        kept = [(original, path) for original, path in enumerate(paths) if os.path.isfile(path)]
        if not kept:
            return None
        positions = [original for original, _path in kept]
        songs = tuple(path for _original, path in kept)
        if index not in positions:
            return cls(songs)  # The song itself is gone: keep the rest of the queue.
        return cls(songs, positions.index(index), max(0.0, position))

    def save(self, library: Library) -> None:
        library.set_setting(KEY, json.dumps(asdict(self)))

    @staticmethod
    def forget(library: Library) -> None:
        with library.connect() as db:
            db.execute("DELETE FROM settings WHERE key = ?", (KEY,))
