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


async def test_amp_keys_tune_mpv_live_and_persist(tmp_path, audio_factory):
    library, paths = populated(tmp_path, audio_factory)
    player = AmpPlayer()
    app = KirlianApp(library, player=player)
    async with app.run_test(size=(120, 44)) as pilot:
        await pilot.pause()
        await pilot.press("w")
        panel = app.query_one("#amp")
        assert panel.display and app.focused is panel
        # Arrows belong to the amp: no navigation, no playback.
        await pilot.press("left", "up", "up")  # 500 Hz +2: turns the equalizer on.
        await pilot.pause(0.1)
        assert app.amp.enabled and app.amp.gains[4] == 2
        assert player.calls[0][0] == "apply" and "equalizer@b4" in player.calls[0][1]
        assert app.view == "albums"
        await pilot.press("up")
        await pilot.pause(0.1)
        assert player.calls[-1] == ("tune", "equalizer@b4", "gain", "3")
        await pilot.press("left", "left", "left", "left", "left", "down")  # Preamp -1 dB.
        await pilot.pause(0.1)
        assert player.calls[-1] == ("tune", "volume@pre", "volume", "-1dB")
        await pilot.press("g", "full_stop", "full_stop")  # Custom → Flat → Bass.
        await pilot.pause(0.1)
        assert app.amp.replaygain == "track" and app.amp.preset == "Bass"
        await pilot.press("e")
        await pilot.pause(0.1)
        assert player.calls[-1] == ("apply", METER, "track")  # Off removes the chain.
        await pilot.press("w")
        assert app.focused is not panel and not panel.display
        await pilot.pause(0.5)
    saved = AmpSettings.load(library)
    assert saved.preset == "Bass" and saved.replaygain == "track" and not saved.enabled
    assert not any(call[0] in {"play", "pause"} for call in player.calls)


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
        assert not app.screen.show_horizontal_scrollbar
