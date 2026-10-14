"""Read local cover art without changing tags, downloading, or persisting images."""

from __future__ import annotations

import base64
import io
import warnings
from collections.abc import Iterator
from pathlib import Path

import mutagen
from mutagen.flac import Picture
from PIL import Image, ImageOps

from .library import DISC_FOLDER

MAX_BYTES = 12 * 1024 * 1024
MAX_PIXELS = 16_000_000
MAX_EDGE = 1024
COVER_NAMES = ("cover", "folder", "front", "album", "artwork")
EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")


def embedded(path: Path) -> Iterator[bytes]:
    audio = mutagen.File(path)
    if audio is None:
        return
    pictures = getattr(audio, "pictures", [])
    for picture in sorted(pictures, key=lambda item: item.type != 3):
        yield picture.data
    tags = audio.tags
    if not tags:
        return
    if hasattr(tags, "getall"):
        for picture in sorted(tags.getall("APIC"), key=lambda item: item.type != 3):
            yield picture.data
    yield from tags.get("covr", [])
    for value in tags.get("metadata_block_picture", []):
        if len(value) <= MAX_BYTES * 4 // 3 + 4:
            try:
                yield Picture(base64.b64decode(value, validate=True)).data
            except (ValueError, mutagen.MutagenError):
                continue


def decode(data: bytes) -> Image.Image | None:
    if not data or len(data) > MAX_BYTES:
        return None
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as source:
                if source.width * source.height > MAX_PIXELS:
                    return None
                # Decode and normalize off the UI thread; never hand it lazy file IO.
                source.thumbnail((MAX_EDGE, MAX_EDGE), Image.Resampling.LANCZOS)
                image = ImageOps.exif_transpose(source).convert("RGBA")
                background = Image.new("RGBA", image.size, "#100f13")
                background.alpha_composite(image)
                return background.convert("RGB")
    except (OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        return None


def load_artwork(paths: tuple[str, ...]) -> Image.Image | None:
    folders: list[Path] = []
    for name in paths:
        path = Path(name)
        try:
            for data in embedded(path):
                if image := decode(data):
                    return image
        except (OSError, ValueError, EOFError, mutagen.MutagenError):
            pass
        for folder in (path.parent,):
            if folder not in folders:
                folders.append(folder)
            if DISC_FOLDER.fullmatch(folder.name) and folder.parent not in folders:
                folders.append(folder.parent)
    for folder in folders:
        try:
            entries = {
                entry.name.casefold(): entry for entry in folder.iterdir() if entry.is_file()
            }
            for name in COVER_NAMES:
                for suffix in EXTENSIONS:
                    path = entries.get(name + suffix)
                    if path and path.stat().st_size <= MAX_BYTES:
                        # Bound the actual read too, in case the file changes after stat.
                        with path.open("rb") as source:
                            image = decode(source.read(MAX_BYTES + 1))
                        if image:
                            return image
        except (OSError, ValueError):
            continue
    return None
