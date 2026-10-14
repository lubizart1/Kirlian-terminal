import hashlib
import io

from mutagen.id3 import APIC
from mutagen.wave import WAVE
from PIL import Image

from kirlian_terminal.artwork import MAX_BYTES, decode, load_artwork


def picture(color):
    output = io.BytesIO()
    Image.new("RGB", (50, 50), color).save(output, format="PNG")
    return output.getvalue()


def test_front_cover_preferred_and_original_unchanged(tmp_path, audio_factory):
    path = audio_factory(tmp_path / "music.wav", title="Song")
    audio = WAVE(path)
    audio.tags.add(APIC(mime="image/png", type=4, desc="back", data=picture("blue")))
    audio.tags.add(APIC(mime="image/png", type=3, desc="front", data=picture("red")))
    audio.save()
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    Image.new("RGB", (50, 50), "green").save(tmp_path / "cover.png")
    image = load_artwork((str(path),))
    assert image.getpixel((0, 0)) == (255, 0, 0)
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before


def test_corrupt_embedded_falls_back_to_disc_parent_cover(tmp_path, audio_factory):
    path = audio_factory(tmp_path / "CD 1" / "music.wav", title="Song")
    audio = WAVE(path)
    audio.tags.add(APIC(mime="image/png", type=3, data=b"broken"))
    audio.save()
    Image.new("RGB", (50, 50), "blue").save(tmp_path / "Folder.PNG")
    assert load_artwork((str(path),)).getpixel((0, 0)) == (0, 0, 255)


def test_missing_corrupt_and_oversized_artwork(tmp_path):
    assert load_artwork((str(tmp_path / "missing.mp3"),)) is None
    assert decode(b"not an image") is None
    assert decode(b"0" * (MAX_BYTES + 1)) is None
    output = io.BytesIO()
    Image.new("1", (5000, 4000)).save(output, "PNG")
    assert decode(output.getvalue()) is None


async def test_slow_old_cover_cannot_replace_current_selection(
    tmp_path, audio_factory, monkeypatch
):
    import threading

    from test_app import FakePlayer, populated
    from textual.widgets import DataTable

    import kirlian_terminal.app as app_module

    library, _ = populated(tmp_path, audio_factory)
    root = tmp_path / "Music"
    audio_factory(root / "other.wav", title="Other song", album="Other", artist="Artist")
    library.scan(root, lambda _: None, threading.Event())
    started, release = threading.Event(), threading.Event()

    def slow_loader(paths):
        if any(path.endswith("other.wav") for path in paths):
            return Image.new("RGB", (10, 10), "blue")
        started.set()
        release.wait(10)
        return Image.new("RGB", (10, 10), "red")

    monkeypatch.setattr(app_module, "load_artwork", slow_loader)
    app = app_module.KirlianApp(library, player=FakePlayer())
    async with app.run_test(size=(120, 32)) as pilot:
        try:
            for _ in range(50):
                await pilot.pause(0.03)
                if started.is_set():
                    break
            assert started.is_set()
            # Navigate normally while the old cover is still decoding.
            app.query_one(DataTable).move_cursor(row=1)
            for _ in range(50):
                await pilot.pause(0.03)
                image = app.query_one("#cover").image
                if image is not None and image.getpixel((0, 0)) == (0, 0, 255):
                    break
            assert app.query_one("#cover").image.getpixel((0, 0)) == (0, 0, 255)
        finally:
            release.set()
        await pilot.pause(0.2)
        assert app.query_one("#cover").image.getpixel((0, 0)) == (0, 0, 255)
