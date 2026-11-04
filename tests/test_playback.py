# SPDX-License-Identifier: GPL-3.0-or-later
import asyncio
import shutil

import pytest

from kirlian_terminal.playback import PlaybackError, PlaybackState, Player


async def wait_until(predicate, timeout=6):
    async with asyncio.timeout(timeout):
        while not predicate():
            await asyncio.sleep(0.02)


def test_observed_state_and_error_events():
    state = PlaybackState()
    for name, value in [
        ("pause", False),
        ("idle-active", False),
        ("time-pos", 12.5),
        ("duration", 45),
        ("volume", 23),
        ("playlist-pos", 0),
        ("path", "/music/a.wav"),
        ("playlist", [{"filename": "/music/a.wav"}]),
    ]:
        state.consume({"event": "property-change", "name": name, "data": value})
    assert not state.paused and not state.idle
    assert (state.position, state.duration, state.volume, state.index) == (12.5, 45, 23, 0)
    state.consume({"event": "end-file", "reason": "error", "file_error": "unrecognized format"})
    assert "unrecognized format" in state.error
    state.consume({"event": "start-file"})
    assert not state.error and state.position == state.duration == 0
    assert state.loading
    state.consume({"event": "file-loaded"})
    assert not state.loading
    state.consume({"event": "property-change", "name": "playlist-pos"})
    assert state.index == -1


async def test_missing_mpv(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda _: None)
    with pytest.raises(PlaybackError, match="mpv is missing"):
        await Player().start()


async def test_seek_while_loading_has_clear_error():
    player = Player()
    player.state.loading = True
    with pytest.raises(PlaybackError, match="Wait for a track to start"):
        await player.control("seek", 5, "relative+exact")


@pytest.mark.integration
@pytest.mark.skipif(not shutil.which("mpv"), reason="mpv not installed")
async def test_real_mpv_queue_controls_transitions_and_owned_cleanup(tmp_path, audio_factory):
    paths = [str(audio_factory(tmp_path / f"É album {n}.wav", seconds=3)) for n in range(3)]
    player = Player(extra_args=("--ao=null",))
    other = Player(extra_args=("--ao=null",))
    try:
        await player.start()
        await other.start()
        pid = player.process.pid
        await player.play(paths[:2], index=1)
        await wait_until(
            lambda: (
                player.state.index == 1
                and player.state.path == paths[1]
                and not player.state.loading
                and player.state.position > 0.05
            )
        )
        assert player.state.path == paths[1]
        await player.toggle_pause()
        await wait_until(lambda: player.state.paused)
        await player.command("seek", 1, "absolute+exact")
        # Ask mpv where it is: a paused player does not always report the new position.
        # Under load, a paused audio-only seek can settle up to one audio buffer
        # (--audio-buffer, 0.2 s by default) short of its target: 1.0 reads as 0.81.
        async with asyncio.timeout(6):
            while abs((await player.command("get_property", "time-pos") or 0) - 1) > 0.25:
                await asyncio.sleep(0.02)
        await player.command("set_property", "volume", 35)
        await wait_until(lambda: player.state.volume == 35)
        await player.append([paths[2], paths[2]])
        await wait_until(lambda: len(player.state.playlist) == 4)
        assert player.state.index == 1 and player.state.paused
        assert [item["filename"] for item in player.state.playlist] == paths + [paths[2]]
        await player.command("playlist-prev", "weak")
        await wait_until(lambda: player.state.index == 0)
        await player.command("playlist-next", "weak")
        await wait_until(lambda: player.state.index == 1)
        await player.jump(2)
        await wait_until(
            lambda: (
                player.state.index == 2
                and player.state.path == paths[2]
                and not player.state.loading
                and player.state.position > 0.05
                and not player.state.paused
            )
        )
        await player.command("seek", 2.7, "absolute+exact")
        await wait_until(lambda: player.state.index == 3)
        assert player.process.pid == pid
        await player.close()
        assert player.process.returncode is not None
        assert other.process.returncode is None
    finally:
        await player.close()
        await other.close()


@pytest.mark.integration
@pytest.mark.skipif(not shutil.which("mpv"), reason="mpv not installed")
async def test_append_idle_and_bad_file_are_visible(tmp_path, audio_factory):
    good = str(audio_factory(tmp_path / "good.wav"))
    bad = tmp_path / "bad.mp3"
    bad.write_text("unplayable")
    errors = []
    player = Player(
        on_change=lambda state: errors.append(state.error) if state.error else None,
        extra_args=("--ao=null",),
    )
    try:
        await player.start()
        await player.append([good])
        await wait_until(lambda: len(player.state.playlist) == 1)
        assert player.state.idle
        await player.toggle_pause()
        await wait_until(lambda: not player.state.idle)
        await player.play([str(bad)])
        await wait_until(lambda: bool(errors))
        assert "Cannot play" in errors[-1]
        assert player.process.returncode is None
    finally:
        await player.close()


@pytest.mark.integration
@pytest.mark.skipif(not shutil.which("mpv"), reason="mpv not installed")
async def test_unexpected_process_exit_is_visible(tmp_path, audio_factory):
    song = str(audio_factory(tmp_path / "sample.wav", seconds=3))
    player = Player(extra_args=("--ao=null",))
    try:
        await player.start()
        await player.play([song])
        await wait_until(lambda: not player.state.idle)
        player.process.terminate()
        await player.process.wait()
        await wait_until(lambda: "stopped unexpectedly" in player.state.error)
        assert player.state.idle
        with pytest.raises(PlaybackError):
            await player.command("get_property", "pause")
    finally:
        await player.close()


@pytest.mark.integration
@pytest.mark.skipif(not shutil.which("mpv"), reason="mpv not installed")
async def test_real_mpv_resumes_a_saved_queue_paused_at_the_saved_place(tmp_path, audio_factory):
    paths = [str(audio_factory(tmp_path / f"{n}.wav", seconds=6)) for n in range(4)]
    player = Player(extra_args=("--ao=null",))
    await player.start()
    try:
        await player.resume(paths, 2, 3.0)

        def order():
            return [item["filename"] for item in player.state.playlist]

        # The original order; mpv reports each move separately, so wait for the last.
        await wait_until(lambda: order() == paths and player.state.position >= 2.9)
        state = player.state
        assert state.index == 2 and state.path == paths[2]
        assert state.paused and not state.idle  # Ready, but silent until the listener plays.
        await asyncio.sleep(0.3)
        assert 2.9 <= player.state.position < 3.2
    finally:
        await player.close()
