"""Optional codec smoke checks: generated audio, no network or personal music."""

import asyncio
import shutil
import subprocess

import pytest

from kirlian_terminal.library import read_track
from kirlian_terminal.playback import Player


@pytest.mark.integration
@pytest.mark.skipif(
    not shutil.which("mpv") or not shutil.which("ffmpeg"),
    reason="mpv and ffmpeg are needed for generated codec fixtures",
)
@pytest.mark.parametrize(
    "extension,codec",
    [
        ("mp3", "libmp3lame"),
        ("flac", "flac"),
        ("m4a", "aac"),
        ("aac", "aac"),
        ("ogg", "vorbis"),
        ("opus", "libopus"),
        ("wav", "pcm_s16le"),
    ],
)
async def test_installed_engine_decodes_format(tmp_path, audio_factory, extension, codec):
    source = audio_factory(tmp_path / "source.wav", seconds=2)
    target = tmp_path / f"É sample with spaces.{extension}"
    # FFmpeg's native Vorbis encoder is available without the optional libvorbis build.
    options = ["-strict", "-2", "-ac", "2", "-ar", "48000"] if codec == "vorbis" else []
    encoded = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(source), "-c:a", codec, *options, str(target)],
        capture_output=True,
        timeout=30,
    )
    assert encoded.returncode == 0, encoded.stderr.decode(errors="replace")
    assert read_track(target).format == extension.upper()
    player = Player(extra_args=("--ao=null",))
    try:
        await player.start()
        await player.play([str(target)])
        async with asyncio.timeout(5):
            while player.state.position < 0.1:
                assert not player.state.error
                await asyncio.sleep(0.02)
        assert player.state.path == str(target)
    finally:
        await player.close()
