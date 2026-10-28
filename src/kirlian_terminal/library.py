# SPDX-License-Identifier: GPL-3.0-or-later
"""Read-only music discovery and application-owned library storage."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import mutagen

EXTENSIONS = {".mp3", ".flac", ".m4a", ".aac", ".ogg", ".oga", ".opus", ".wav"}
DISC_FOLDER = re.compile(r"(?:cd|disc|disk)[\s._-]*\d+", re.IGNORECASE)


def number(value: str, fallback: int = 0) -> int:
    match = re.match(r"\s*(\d+)", value)
    return int(match[1]) if match else fallback


def display_text(value: object) -> str:
    """Prevent embedded terminal controls without interpreting tag markup."""
    return " ".join("".join(c if c.isprintable() else " " for c in str(value)).split())


@dataclass(frozen=True)
class Track:
    path: str
    title: str
    artist: str
    album: str
    album_artist: str
    album_id: str
    disc: int
    track: int
    duration: float
    year: str
    format: str
    available: bool = True


@dataclass(frozen=True)
class Album:
    id: str
    title: str
    artist: str
    tracks: tuple[Track, ...]


@dataclass(frozen=True)
class ScanProgress:
    indexed: int
    skipped: int
    done: bool = False
    error: str = ""
    blocked: int = 0


def read_track(path: Path) -> Track:
    audio = mutagen.File(path, easy=True)
    # Raw AAC may be playable but have no tags; let mpv determine playback support.
    if audio is None and path.suffix.lower() != ".aac":
        raise ValueError("Unrecognized audio")
    tags = audio.tags if audio is not None and audio.tags else {}

    def tag(key: str, id3: str = "", default: str = "") -> str:
        value = tags.get(key, tags.get(id3, [default]))
        if hasattr(value, "text"):
            value = value.text
        if isinstance(value, (list, tuple)):
            value = value[0] if value else default
        return display_text(value) or default

    release = path.parent
    disc_match = DISC_FOLDER.fullmatch(release.name)
    if disc_match:
        release = release.parent
    album = tag("album", "TALB", display_text(release.name))
    artist = tag("artist", "TPE1", "Unknown artist")
    compilation = tag("compilation", "TCMP") in {"1", "True", "true"}
    album_artist = tag("albumartist", "TPE2", "Various Artists" if compilation else artist)
    identity = json.dumps([str(release), album_artist.casefold(), album.casefold()])
    album_id = hashlib.sha256(identity.encode()).hexdigest()[:24]
    inferred_disc = number(re.search(r"\d+", path.parent.name)[0]) if disc_match else 1
    return Track(
        path=str(path),
        title=tag("title", "TIT2", display_text(path.stem)),
        artist=artist,
        album=album,
        album_artist=album_artist,
        album_id=album_id,
        disc=number(tag("discnumber", "TPOS"), inferred_disc),
        track=number(tag("tracknumber", "TRCK"), number(path.stem)),
        duration=float(getattr(getattr(audio, "info", None), "length", 0)),
        year=tag("date", "TDRC")[:4],
        format=path.suffix[1:].upper(),
    )


class Library:
    def __init__(self, database: Path) -> None:
        self.database = database
        database.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS tracks (
                    path TEXT PRIMARY KEY, root TEXT NOT NULL, title TEXT NOT NULL,
                    artist TEXT NOT NULL, album TEXT NOT NULL, album_artist TEXT NOT NULL,
                    album_id TEXT NOT NULL, disc INTEGER NOT NULL, track INTEGER NOT NULL,
                    duration REAL NOT NULL, year TEXT NOT NULL, format TEXT NOT NULL,
                    available INTEGER NOT NULL DEFAULT 1
                );
                CREATE INDEX IF NOT EXISTS tracks_album ON tracks(album_id);
            """)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.database, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def setting(self, key: str) -> str | None:
        with self.connect() as db:
            row = db.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
            return row[0] if row else None

    def set_setting(self, key: str, value: str) -> None:
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO settings VALUES (?, ?)", (key, value))

    def tracks(self) -> list[Track]:
        root = self.setting("music_folder")
        with self.connect() as db:
            rows = db.execute("SELECT * FROM tracks WHERE root = ?", (root,)).fetchall()
        return [Track(**{k: row[k] for k in Track.__dataclass_fields__}) for row in rows]

    def scan(
        self, root: Path, report: Callable[[ScanProgress], None], stop: threading.Event
    ) -> None:
        root = root.expanduser().resolve()
        if not root.is_dir() or not os.access(root, os.R_OK | os.X_OK):
            report(ScanProgress(0, 0, True, "Choose a readable music folder."))
            return
        indexed = skipped = blocked = 0
        seen: set[str] = set()
        last_report = time.monotonic()

        def walk_error(error: OSError) -> None:
            nonlocal skipped, blocked
            skipped += 1
            blocked += isinstance(error, PermissionError)

        try:
            self.set_setting("music_folder", str(root))
            with self.connect() as db:
                for directory, _, files in os.walk(root, onerror=walk_error):
                    for filename in sorted(files):
                        if stop.is_set():
                            db.commit()
                            return
                        path = Path(directory, filename)
                        if path.suffix.lower() not in EXTENSIONS:
                            continue
                        seen.add(str(path))
                        try:
                            track = read_track(path)
                            values = vars(track)
                            db.execute(
                                """INSERT OR REPLACE INTO tracks VALUES (
                                    :path, :root, :title, :artist, :album, :album_artist,
                                    :album_id, :disc, :track, :duration, :year, :format, :available
                                )""",
                                {**values, "root": str(root)},
                            )
                            indexed += 1
                        except (OSError, ValueError, mutagen.MutagenError, UnicodeError):
                            skipped += 1
                            db.execute("UPDATE tracks SET available=0 WHERE path=?", (str(path),))
                        if time.monotonic() - last_report > 0.15:
                            db.commit()
                            report(ScanProgress(indexed, skipped))
                            last_report = time.monotonic()
                if stop.is_set():
                    return
                known = db.execute("SELECT path FROM tracks WHERE root=?", (str(root),)).fetchall()
                db.executemany(
                    "UPDATE tracks SET available=0 WHERE path=?",
                    [(row[0],) for row in known if row[0] not in seen],
                )
            report(ScanProgress(indexed, skipped, True, blocked=blocked))
        except (OSError, sqlite3.Error) as error:
            report(ScanProgress(indexed, skipped, True, f"Could not finish indexing: {error}"))


def albums_from(tracks: list[Track]) -> list[Album]:
    grouped: dict[str, list[Track]] = {}
    for track in tracks:
        grouped.setdefault(track.album_id, []).append(track)
    albums = []
    for album_id, members in grouped.items():
        members.sort(key=lambda t: (t.disc, t.track, t.path.casefold()))
        first = members[0]
        albums.append(Album(album_id, first.album, first.album_artist, tuple(members)))
    return sorted(albums, key=lambda a: (a.artist.casefold(), a.title.casefold(), a.id))
