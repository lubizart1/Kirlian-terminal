# SPDX-License-Identifier: GPL-3.0-or-later
"""Where to stream or buy a record: each store's own search, built locally from tags.

Nothing is sent anywhere until the listener picks a store; then the browser opens
that store's search for the album's artist and title.
"""

from __future__ import annotations

from urllib.parse import quote, quote_plus

from .library import Album

# (id, name, search URL with {query}). Search pages need no account or API key.
STORES = (
    ("spotify", "Spotify", "https://open.spotify.com/search/{path}"),
    ("apple", "Apple Music", "https://music.apple.com/search?term={query}"),
    ("qobuz", "Qobuz", "https://www.qobuz.com/search?q={query}"),
    ("bandcamp", "Bandcamp", "https://bandcamp.com/search?q={query}&item_type=a"),
)


def searchable(album: Album) -> bool:
    """Only albums named by their tags; folder names stand in for the rest."""
    return all(track.tagged for track in album.tracks)


def store_url(store_id: str, album: Album) -> str:
    template = next(url for sid, _name, url in STORES if sid == store_id)
    terms = f"{album.artist} {album.title}"
    return template.format(path=quote(terms, safe=""), query=quote_plus(terms))
