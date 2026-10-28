# SPDX-License-Identifier: GPL-3.0-or-later
from kirlian_terminal.library import Library
from kirlian_terminal.playlists import Playlists


def test_duplicates_order_moves_and_removal(tmp_path):
    playlists = Playlists(Library(tmp_path / "library.db"))
    evening = playlists.create("Evening")
    playlists.add(evening, ["/m/a.flac", "/m/b.flac"])
    playlists.add(evening, ["/m/a.flac"])
    entries = playlists.entries(evening)
    assert [e.path for e in entries] == ["/m/a.flac", "/m/b.flac", "/m/a.flac"]

    assert not playlists.move(evening, entries[0].id, -1)
    assert not playlists.move(evening, entries[2].id, 1)
    assert playlists.move(evening, entries[2].id, -1)
    assert [e.id for e in playlists.entries(evening)] == [
        entries[0].id,
        entries[2].id,
        entries[1].id,
    ]

    # Removing one copy of a duplicate keeps the other.
    playlists.remove(entries[0].id)
    assert [e.path for e in playlists.entries(evening)] == ["/m/a.flac", "/m/b.flac"]
    playlists.add(evening, ["/m/c.flac"])
    assert playlists.entries(evening)[-1].path == "/m/c.flac"


def test_rename_and_delete_leave_other_playlists_and_files(tmp_path, audio_factory):
    song = audio_factory(tmp_path / "Music" / "song.wav")
    library = Library(tmp_path / "library.db")
    playlists = Playlists(library)
    keep, gone = playlists.create("Keep"), playlists.create("Gone")
    playlists.add(keep, [str(song)])
    playlists.add(gone, [str(song)])
    playlists.rename(keep, "Favourites")
    playlists.delete(gone)

    assert [(p.name, p.size) for p in playlists.all()] == [("Favourites", 1)]
    assert playlists.entries(gone) == []
    assert song.exists()
    # Saved playlists survive reopening the database.
    assert [p.name for p in Playlists(Library(tmp_path / "library.db")).all()] == ["Favourites"]
