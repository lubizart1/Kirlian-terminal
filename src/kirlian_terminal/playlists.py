"""Saved playlists in the application database. Entries reference files by path."""

from __future__ import annotations

from dataclasses import dataclass

from .library import Library


@dataclass(frozen=True)
class Playlist:
    id: int
    name: str
    size: int


@dataclass(frozen=True)
class Entry:
    id: int
    path: str


class Playlists:
    """Entries keep their own ids so intentional duplicates stay distinct."""

    def __init__(self, library: Library) -> None:
        self.library = library
        with library.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS playlists (
                    id INTEGER PRIMARY KEY, name TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS playlist_entries (
                    id INTEGER PRIMARY KEY,
                    playlist_id INTEGER NOT NULL REFERENCES playlists(id),
                    position INTEGER NOT NULL,
                    path TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS playlist_entries_order
                    ON playlist_entries(playlist_id, position);
            """)

    def all(self) -> list[Playlist]:
        with self.library.connect() as db:
            rows = db.execute("""
                SELECT p.id, p.name, COUNT(e.id) FROM playlists p
                LEFT JOIN playlist_entries e ON e.playlist_id = p.id
                GROUP BY p.id ORDER BY p.name COLLATE NOCASE, p.id
            """).fetchall()
        return [Playlist(*row) for row in rows]

    def create(self, name: str) -> int:
        with self.library.connect() as db:
            return db.execute("INSERT INTO playlists(name) VALUES (?)", (name,)).lastrowid

    def rename(self, playlist_id: int, name: str) -> None:
        with self.library.connect() as db:
            db.execute("UPDATE playlists SET name = ? WHERE id = ?", (name, playlist_id))

    def delete(self, playlist_id: int) -> None:
        with self.library.connect() as db:
            db.execute("DELETE FROM playlist_entries WHERE playlist_id = ?", (playlist_id,))
            db.execute("DELETE FROM playlists WHERE id = ?", (playlist_id,))

    def entries(self, playlist_id: int) -> list[Entry]:
        with self.library.connect() as db:
            rows = db.execute(
                "SELECT id, path FROM playlist_entries WHERE playlist_id = ? ORDER BY position",
                (playlist_id,),
            ).fetchall()
        return [Entry(*row) for row in rows]

    def add(self, playlist_id: int, paths: list[str]) -> None:
        with self.library.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            end = db.execute(
                "SELECT COALESCE(MAX(position), -1) FROM playlist_entries WHERE playlist_id = ?",
                (playlist_id,),
            ).fetchone()[0]
            db.executemany(
                "INSERT INTO playlist_entries(playlist_id, position, path) VALUES (?, ?, ?)",
                [(playlist_id, end + 1 + offset, path) for offset, path in enumerate(paths)],
            )

    def remove(self, entry_id: int) -> None:
        with self.library.connect() as db:
            db.execute("DELETE FROM playlist_entries WHERE id = ?", (entry_id,))

    def move(self, playlist_id: int, entry_id: int, offset: int) -> bool:
        """Swap an entry with its neighbour. Returns False at either end."""
        with self.library.connect() as db:
            db.execute("BEGIN IMMEDIATE")  # Rapid moves must not reorder from a stale read.
            ids = [
                row[0]
                for row in db.execute(
                    "SELECT id FROM playlist_entries WHERE playlist_id = ? ORDER BY position",
                    (playlist_id,),
                )
            ]
            if entry_id not in ids:
                return False
            index = ids.index(entry_id)
            target = index + offset
            if not 0 <= target < len(ids):
                return False
            ids[index], ids[target] = ids[target], ids[index]
            db.executemany(
                "UPDATE playlist_entries SET position = ? WHERE id = ?",
                [(position, entry) for position, entry in enumerate(ids)],
            )
        return True
