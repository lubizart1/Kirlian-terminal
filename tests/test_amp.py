# SPDX-License-Identifier: GPL-3.0-or-later
import json

import pytest
from test_app import FakePlayer, populated

from kirlian_terminal.app import KirlianApp, PlayerUpdate
from kirlian_terminal.audio import BANDS, METER, PRESETS, AmpSettings, Levels, Reaction
from kirlian_terminal.library import Library
from kirlian_terminal.playback import PlaybackState


class AmpPlayer(FakePlayer):
    """Records equalizer traffic and serves fixed levels."""

    def __init__(self):
        super().__init__()
        self.reading = Levels(rms=(-12.0, -14.0), peak=(-3.0, -5.0), centroid=3000, flux=0.05)

    async def apply_amp(self, amp):
        self.calls.append(("apply", amp.filters(), amp.replaygain))

    async def tune(self, target, command, value):
        self.calls.append(("tune", target, command, value))

    async def levels(self):
        return self.reading


def test_filters_are_removed_entirely_when_the_equalizer_is_off():
    assert AmpSettings().filters() == METER
    on = AmpSettings(enabled=True, preamp=-3, balance=0.5).with_gain(5, 4)
    chain = on.filters()
    assert chain.startswith("@eq:lavfi=[") and chain.endswith(METER)
    assert "equalizer@b5=f=1000:t=o:w=1:g=4" in chain
    assert "volume@pre=volume=-3dB" in chain and "balance_out=0.5" in chain
    assert chain.count("equalizer@b") == len(BANDS)


def test_settings_clamp_and_survive_bad_storage(tmp_path):
    library = Library(tmp_path / "library.db")
    amp = AmpSettings().with_gain(0, 99).with_gain(9, -99)
    assert amp.gains[0] == 12 and amp.gains[9] == -12 and amp.preset == "" and amp.enabled
    amp.save(library)
    assert AmpSettings.load(library) == amp
    library.set_setting("amp", json.dumps({"gains": [1, 2], "preamp": 40, "replaygain": "x"}))
    loaded = AmpSettings.load(library)
    assert loaded.gains == PRESETS["Flat"] and loaded.preamp == 6 and loaded.replaygain == "no"
    library.set_setting("amp", "not json")
    assert AmpSettings.load(library) == AmpSettings()


def test_levels_parse_mono_and_missing_values():
    mono = Levels.parse({"lavfi.astats.1.RMS_level": "-20", "lavfi.astats.1.Peak_level": "-inf"})
    assert mono.rms == (-20.0, -20.0)
    assert mono.peak == (-60.0, -60.0)
    assert Levels.parse(None) == Levels()
    assert Levels(rms=(-6.0, -40.0)).energy == 1.0
    assert Levels(rms=(-60.0, -60.0)).energy == 0.0
    assert Levels(centroid=200).brightness == 0.0 and Levels(centroid=8000).brightness == 1.0


def test_reaction_speeds_up_with_loudness_and_sparks_on_hits():
    reaction = Reaction()
    quiet = Levels(rms=(-40.0, -40.0), flux=0.01)
    for _ in range(20):
        reaction.feed(quiet)
    slow = reaction.rate
    for _ in range(20):
        reaction.feed(Levels(rms=(-8.0, -8.0), flux=0.01))
    assert reaction.rate > slow + 0.8
    assert not reaction.sparks
    reaction.feed(Levels(rms=(-8.0, -8.0), flux=0.2))  # A sudden spectral change.
    assert len(reaction.sparks) == 1
    reaction.decay(1.0)
    assert not reaction.sparks


async def test_amp_only_displays_and_the_sound_screen_changes_mpv(tmp_path, audio_factory):
    from kirlian_terminal.amp import SoundSettings

    library, paths = populated(tmp_path, audio_factory)
    player = AmpPlayer()
    app = KirlianApp(library, player=player)
    async with app.run_test(size=(120, 46)) as pilot:
        await pilot.pause()
        await pilot.press("w")
        panel = app.query_one("#amp")
        assert panel.display and app.focused is not panel
        await pilot.press("enter")  # The library keeps its keys while the amp is open.
        assert app.view == "album"

        await pilot.press("E")
        await pilot.pause()
        assert isinstance(app.screen, SoundSettings)
        # Rows: equalizer, preset, preamp, balance, ReplayGain, speed, pitch, tape, bands.
        await pilot.press("j", "right", "right")  # Preset: Flat → Bass → Rock.
        await pilot.pause(0.1)
        assert app.amp.preset == "Rock" and app.amp.enabled
        assert player.calls[0][0] == "apply" and "equalizer@b0" in player.calls[0][1]
        await pilot.press(*["j"] * 8, "right")  # 62 Hz +1 from Rock's +3.
        await pilot.pause(0.1)
        assert app.amp.gains[1] == 4 and app.amp.preset == ""
        assert player.calls[-1] == ("tune", "equalizer@b1", "gain", "4")
        assert "62 Hz" in str(app.screen.query_one("#sound-detail").content)
        await pilot.press("0")
        await pilot.pause(0.1)
        assert app.amp.gains[1] == 0
        await pilot.press(*["k"] * 7, "left")  # Preamp -1 dB.
        await pilot.pause(0.1)
        assert player.calls[-1] == ("tune", "volume@pre", "volume", "-1dB")
        await pilot.press("0")  # Resetting a named row, not a band, must not crash.
        await pilot.pause(0.1)
        assert app.amp.preamp == 0 and app.is_running
        await pilot.press("j", "j", "right")  # ReplayGain: per track.
        await pilot.pause(0.1)
        assert app.amp.replaygain == "track"
        await pilot.press("k", "k", "k", "k", "enter")  # Equalizer off removes the chain.
        await pilot.pause(0.1)
        assert player.calls[-1] == ("apply", METER, "track")
        await pilot.press("escape", "w")
        await pilot.pause(0.5)
        assert not panel.display
    saved = AmpSettings.load(library)
    assert saved.replaygain == "track" and not saved.enabled and saved.gains[0] == 4
    assert not any(call[0] in {"play", "pause"} for call in player.calls)


async def test_speed_pitch_and_tape_reach_mpv_and_reset_next_launch(tmp_path, audio_factory):
    from kirlian_terminal.audio import Tempo

    library, _ = populated(tmp_path, audio_factory)
    player = AmpPlayer()
    sent = []

    async def apply_tempo(tempo):
        sent.append(tempo)

    player.apply_tempo = apply_tempo
    app = KirlianApp(library, player=player)
    async with app.run_test(size=(120, 46)) as pilot:
        await pilot.pause()
        await pilot.press("E", *["j"] * 5, "left", "left", "left")  # Speed 0.85×.
        await pilot.press("j", "right", "right")  # Pitch +2 semitones.
        await pilot.press("j", "enter")  # Tape on.
        await pilot.pause(0.2)
        assert sent[-1] == Tempo(speed=0.85, semitones=2, tape=True)
        assert abs(sent[-1].pitch - 2 ** (2 / 12)) < 1e-9
        assert "+2 semitones" in app.query_one("#amp").render().plain
        await pilot.press("k", "0", "k", "0")  # Reset pitch and speed.
        await pilot.pause(0.2)
        assert sent[-1] == Tempo(tape=True)
    assert KirlianApp(library, player=AmpPlayer()).tempo == Tempo()


async def test_levels_reach_meters_and_ribbon_only_while_playing(tmp_path, audio_factory):
    library, paths = populated(tmp_path, audio_factory)
    library.set_setting("amp", json.dumps({"visible": True}))
    player = AmpPlayer()
    app = KirlianApp(library, player=player)
    async with app.run_test(size=(120, 44)) as pilot:
        await pilot.pause(0.2)
        panel = app.query_one("#amp")
        assert panel.levels == Levels()
        state = PlaybackState(path=paths[0], paused=False, idle=False, started_serial=1)
        app.on_player_update(PlayerUpdate(state))
        for _ in range(30):
            await pilot.pause(0.05)
            if panel.levels.rms[0] == -12.0:
                break
        assert panel.levels.rms == (-12.0, -14.0)
        assert panel.hold[0] == -3.0
        assert app.query_one("#animation").reaction.energy > 0
        assert "-12 dB" in panel.render().plain


@pytest.mark.parametrize("size", [(80, 24), (120, 44)])
async def test_amp_fits_small_and_large_windows(tmp_path, audio_factory, size):
    library, _ = populated(tmp_path, audio_factory)
    app = KirlianApp(library, player=AmpPlayer())
    async with app.run_test(size=size) as pilot:
        await pilot.press("w")
        await pilot.pause()
        panel = app.query_one("#amp")
        assert panel.compact == (size[1] < 36)
        assert panel.region.bottom <= app.query_one("#animation").region.y
        assert app.focused is not panel
        assert not app.screen.show_horizontal_scrollbar


def test_spectrum_bands_ride_after_the_two_real_channels():
    from kirlian_terminal.audio import SPECTRUM

    metadata = {f"lavfi.astats.{n}.RMS_level": str(-10 - n) for n in range(1, len(SPECTRUM) + 3)}
    levels = Levels.parse(metadata)
    assert levels.rms == (-11.0, -12.0)
    assert len(levels.bands) == len(SPECTRUM) and levels.bands[0] == -13.0
    assert Levels.parse({"lavfi.astats.1.RMS_level": "-9"}).bands == ()
    assert METER.count("bandpass=") == len(SPECTRUM) and "pan=stereo|c0=c0|c1=c1" in METER


async def test_quick_successive_changes_leave_mpv_on_the_latest_settings(tmp_path, audio_factory):
    """Each change is a diff; a slow earlier one must not land after a later one."""
    import asyncio

    class SlowPlayer(AmpPlayer):
        async def tune(self, target, command, value):
            await asyncio.sleep(0.02)
            await super().tune(target, command, value)

    library, _ = populated(tmp_path, audio_factory)
    player = SlowPlayer()
    app = KirlianApp(library, player=player)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.change_amp(app.amp.with_gain(0, 3).with_gain(9, 6))  # Turns it on: one rebuild.
        app.change_amp(app.amp.with_gain(0, 4).with_gain(9, 2))
        app.change_amp(app.amp.with_gain(9, 7))
        await app.workers.wait_for_complete(
            [worker for worker in app.workers if worker.group == "amp-audio"]
        )
        live = {call[1]: call[3] for call in player.calls if call[0] == "tune"}
        assert live == {"equalizer@b0": "4", "equalizer@b9": "7"}


async def test_changed_sound_is_always_shown_and_one_key_resets_it(tmp_path, audio_factory):
    from kirlian_terminal.amp import AmpPanel, SoundSettings
    from kirlian_terminal.audio import Tempo

    library, _ = populated(tmp_path, audio_factory)
    library.set_setting(
        "amp",
        json.dumps({"visible": True, "enabled": True, "preamp": 6, "balance": -0.1}),
    )
    player = AmpPlayer()
    app = KirlianApp(library, player=player)
    async with app.run_test(size=(140, 44)) as pilot:
        await pilot.pause()
        app.tempo_change("pitch", 1)
        panel = app.query_one(AmpPanel)
        line = panel.info_line(140).plain
        assert "Preamp +6 dB" in line and "Balance left 10%" in line and "+1 semitone" in line
        await pilot.press("E", "R")
        await pilot.pause(0.2)
        assert isinstance(app.screen, SoundSettings)
        assert app.amp == AmpSettings(visible=True) and app.tempo == Tempo()
        assert player.calls[-1] == ("apply", METER, "no")  # The chain is gone entirely.
        line = panel.info_line(140).plain
        assert "Preamp" not in line and "Balance" not in line and "semitone" not in line
