import struct
import wave
from pathlib import Path

import pytest
from mutagen.id3 import TALB, TCMP, TCOM, TIT2, TPE1, TPE2, TPOS, TRCK
from mutagen.wave import WAVE


def make_audio(path: Path, seconds: float = 2, **tags: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(8000)
        audio.writeframes(struct.pack("<h", 0) * int(8000 * seconds))
    if tags:
        audio = WAVE(path)
        audio.add_tags()
        frames = {
            "title": TIT2,
            "artist": TPE1,
            "album": TALB,
            "albumartist": TPE2,
            "track": TRCK,
            "disc": TPOS,
            "compilation": TCMP,
            "composer": TCOM,
        }
        for key, value in tags.items():
            audio.tags.add(frames[key](encoding=3, text=[value]))
        audio.save()
    return path


@pytest.fixture
def audio_factory():
    return make_audio
