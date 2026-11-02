# SPDX-License-Identifier: GPL-3.0-or-later
"""What each view lists: rows, heading, breadcrumb, and summary, from plain data."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from .i18n import _, n_
from .library import Album, Track, display_text
from .playlists import Entry, Playlist


def clock(seconds: float) -> str:
    minutes, seconds = divmod(max(0, int(seconds)), 60)
    return f"{minutes}:{seconds:02d}"


@dataclass(frozen=True)
class Row:
    kind: str
    value: str
    title: str
    detail: str = ""
    duration: str = ""


@dataclass(frozen=True)
class Shelf:
    """Everything a view can list. The queue is mpv's playlist as last reported."""

    tracks: list[Track]
    albums: list[Album]
    by_path: dict[str, Track]
    playlists: list[Playlist]
    entries: list[Entry]
    queue: list[dict[str, Any]] = field(default_factory=list)
    queue_index: int = -1
    playing: str = ""  # Path of the song mpv is on, or "" when idle.

    def album(self, album_id: str) -> Album | None:
        return next((album for album in self.albums if album.id == album_id), None)

    def playlist(self, playlist_id: str) -> Playlist | None:
        return next((p for p in self.playlists if str(p.id) == playlist_id), None)

    def track_row(self, track: Track, detail: str | None = None) -> Row:
        marker = "> " if self.playing == track.path else ""
        unavailable = " " + _("[unavailable]") if not track.available else ""
        return Row(
            "track",
            track.path,
            marker + track.title + unavailable,
            detail if detail is not None else track.artist,
            clock(track.duration),
        )


@dataclass(frozen=True)
class Listing:
    heading: str
    rows: list[Row]
    breadcrumb: str
    detail: str
    empty: str


def listing(view: str, value: str, query: str | None, shelf: Shelf) -> Listing:
    """`query` is None outside search; an empty query lists nothing yet."""
    searching = query is not None
    heading = {
        "albums": _("Albums"),
        "artists": _("Artists"),
        "songs": _("Songs"),
        "playlists": _("Playlists"),
        "queue": _("Queue"),
    }.get(view, view.title())
    rows: list[Row] = []
    album = playlist = None
    if searching:
        heading = _("Search")
        if query:
            rows = search(query, shelf)
    elif view == "albums":
        rows = [
            Row("album", a.id, a.title, a.artist, clock(sum(t.duration for t in a.tracks)))
            for a in shelf.albums
        ]
    elif view == "artists":
        rows = [Row("artist", a, a) for a in artists(shelf.tracks)]
    elif view == "songs":
        rows = [shelf.track_row(t) for t in sorted(shelf.tracks, key=lambda t: t.title.casefold())]
    elif view == "album":
        album = shelf.album(value)
        heading = album.title if album else _("Album unavailable")
        if album:
            rows = [
                shelf.track_row(t, f"{t.disc}.{t.track:02d} · {t.artist}") for t in album.tracks
            ]
    elif view == "artist":
        heading = value
        rows = [
            Row("album", a.id, a.title, a.artist)
            for a in shelf.albums
            if any(t.artist == value for t in a.tracks)
        ]
    elif view == "playlists":
        rows = [Row("new-playlist", "", _("+ New playlist"), "")]
        rows.extend(
            Row("playlist", str(p.id), display_text(p.name), f"{p.size}") for p in shelf.playlists
        )
    elif view == "playlist":
        playlist = shelf.playlist(value)
        heading = display_text(playlist.name) if playlist else _("Playlist unavailable")
        for entry in shelf.entries if playlist else []:
            track = shelf.by_path.get(entry.path)
            if track:
                rows.append(replace(shelf.track_row(track), kind="entry", value=str(entry.id)))
            else:
                title = _("{name} [unavailable]", name=display_text(Path(entry.path).name))
                rows.append(Row("entry", str(entry.id), title, ""))
    elif view == "queue":
        for index, item in enumerate(shelf.queue):
            track = shelf.by_path.get(item["filename"])
            title = track.title if track else display_text(Path(item["filename"]).name)
            marker = "> " if index == shelf.queue_index else ""
            rows.append(
                Row(
                    "queue",
                    str(index),
                    marker + title,
                    track.artist if track else "",
                    clock(track.duration) if track else "",
                )
            )
    breadcrumb = (
        _("Albums / {artist}", artist=album.artist) if album else _("Playlists") if playlist else ""
    )
    return Listing(
        heading,
        rows,
        breadcrumb,
        summary(view, searching, rows, album, playlist, shelf),
        empty_text(view, searching),
    )


def artists(tracks: list[Track]) -> list[str]:
    return sorted({t.artist for t in tracks}, key=str.casefold)


def search(query: str, shelf: Shelf) -> list[Row]:
    query = query.casefold().strip()
    if not query:
        return []
    rows = [
        Row("album", a.id, a.title, _("Album · {artist}", artist=a.artist))
        for a in shelf.albums
        if query in f"{a.title} {a.artist}".casefold()
    ]
    rows.extend(
        Row("artist", a, a, _("Artist")) for a in artists(shelf.tracks) if query in a.casefold()
    )
    rows.extend(
        shelf.track_row(t, _("Song · {artist} · {album}", artist=t.artist, album=t.album))
        for t in shelf.tracks
        if query in f"{t.title} {t.artist} {t.album}".casefold()
    )
    rows.extend(
        Row("playlist", str(p.id), display_text(p.name), _("Playlist"))
        for p in shelf.playlists
        if query in p.name.casefold()
    )
    return rows


def summary(
    view: str,
    searching: bool,
    rows: list[Row],
    album: Album | None,
    playlist: Playlist | None,
    shelf: Shelf,
) -> str:
    if album:
        year = album.tracks[0].year
        return (
            f"{year + ' · ' if year else ''}"
            + n_("{n} song", "{n} songs", len(album.tracks))
            + f" · {clock(sum(t.duration for t in album.tracks))}"
        )
    if playlist:
        seconds = sum(
            shelf.by_path[e.path].duration for e in shelf.entries if e.path in shelf.by_path
        )
        return n_("{n} song", "{n} songs", len(rows)) + f" · {clock(seconds)}"
    if searching:
        return n_("{n} result", "{n} results", len(rows))
    counts = {
        "playlists": lambda: n_("{n} playlist", "{n} playlists", len(shelf.playlists)),
        "albums": lambda: n_("{n} album", "{n} albums", len(rows)),
        "artists": lambda: n_("{n} artist", "{n} artists", len(rows)),
        "songs": lambda: n_("{n} song", "{n} songs", len(rows)),
        "queue": lambda: n_("{n} in queue", "{n} in queue", len(rows)),
    }
    return counts[view]() if view in counts else f"{len(rows)} {view}"


def empty_text(view: str, searching: bool) -> str:
    if searching:
        return _("No matching music.")
    if view == "playlist":
        return _("This playlist is empty. Select a song or album elsewhere and press +.")
    if view == "queue":
        return _("Queue is empty. Append with a, or play a track.")
    return _("No music here yet. Press f to choose a folder, or r to rescan.")
