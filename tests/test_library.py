# SPDX-License-Identifier: GPL-3.0-or-later
import hashlib
import os
import threading

import pytest

from kirlian_terminal.library import Library, albums_from, read_track


def scan(library, folder):
    progress = []
    library.scan(folder, progress.append, threading.Event())
    assert progress[-1].done
    assert not progress[-1].error
    return progress[-1]


def test_album_identity_numeric_order_compilation_and_multiple_discs(tmp_path, audio_factory):
    root = tmp_path / "Music with é spaces"
    for disc, track in [(1, 10), (1, 2), (2, 1)]:
        audio_factory(
            root / "Release" / f"CD {disc}" / f"{track}.wav",
            title=f"Song {disc}.{track}",
            album="Same title",
            artist=f"Artist {track}",
            compilation="1",
            track=f"{track}/12",
            disc=f"{disc}/2",
        )
    audio_factory(
        root / "Other edition" / "01.wav", album="Same title", artist="Someone", compilation="1"
    )
    library = Library(tmp_path / "library.db")
    assert scan(library, root).indexed == 4
    albums = albums_from(library.tracks())
    assert len(albums) == 2
    album = next(a for a in albums if len(a.tracks) == 3)
    assert album.artist == "Various Artists"
    assert [(t.disc, t.track) for t in album.tracks] == [(1, 2), (1, 10), (2, 1)]


def test_editions_with_identical_tags_in_one_folder_are_told_apart_by_release_id(
    tmp_path, audio_factory
):
    root = tmp_path / "Flat"
    tags = {"album": "Same", "artist": "Band"}
    for name, release in [("a1", "edition-a"), ("a2", "edition-a"), ("b1", "EDITION-B")]:
        audio_factory(root / f"{name}.wav", title=name, release_id=release, **tags)
    audio_factory(root / "plain.wav", title="plain", **tags)
    library = Library(tmp_path / "library.db")
    scan(library, root)
    sizes = sorted(len(album.tracks) for album in albums_from(library.tracks()))
    assert sizes == [1, 1, 2]  # Edition A, edition B, and the untagged-edition file.


def test_tags_fallbacks_persistence_missing_files_and_no_music_writes(tmp_path, audio_factory):
    root = tmp_path / "Untagged album"
    song = audio_factory(root / "02 A song.wav")
    original = hashlib.sha256(song.read_bytes()).hexdigest()
    (root / "broken.mp3").write_text("not audio")
    (root / "cover.jpg").write_text("not music")
    library = Library(tmp_path / "library.db")
    result = scan(library, root)
    assert (result.indexed, result.skipped) == (1, 1)
    track = Library(library.database).tracks()[0]
    assert (track.title, track.album, track.artist, track.track) == (
        "02 A song",
        "Untagged album",
        "Unknown artist",
        2,
    )
    # Filename and folder stand in for display only; song notes never send them.
    assert not track.tagged
    assert hashlib.sha256(song.read_bytes()).hexdigest() == original
    song.unlink()
    scan(library, root)
    assert not library.tracks()[0].available
    audio_factory(song)
    scan(library, root)
    assert library.tracks()[0].available


def test_album_artist_and_controls_in_tags(tmp_path, audio_factory):
    song = audio_factory(
        tmp_path / "01.wav",
        album="[bold]Album[/bold]",
        title="Hi\x1b[2J",
        artist="Guest",
        albumartist="Main artist",
    )
    track = read_track(song)
    assert track.album_artist == "Main artist"
    assert "\x1b" not in track.title
    assert track.album == "[bold]Album[/bold]"


def test_invalid_folder_does_not_replace_previous_library(tmp_path, audio_factory):
    root = tmp_path / "Music"
    audio_factory(root / "1.wav")
    library = Library(tmp_path / "library.db")
    scan(library, root)
    progress = []
    library.scan(tmp_path / "missing", progress.append, threading.Event())
    assert progress[-1].error
    assert library.setting("music_folder") == str(root)
    assert len(library.tracks()) == 1


@pytest.mark.skipif(hasattr(os, "geteuid") and os.geteuid() == 0, reason="root reads any folder")
def test_permission_denied_subfolder_is_reported_as_blocked(tmp_path, audio_factory):
    root = tmp_path / "Music"
    audio_factory(root / "Private" / "1.wav")
    (root / "Private").chmod(0)
    try:
        result = scan(Library(tmp_path / "library.db"), root)
    finally:
        (root / "Private").chmod(0o755)
    assert (result.indexed, result.skipped, result.blocked) == (0, 1, 1)
