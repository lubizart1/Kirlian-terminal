# SPDX-License-Identifier: GPL-3.0-or-later
import hashlib
from dataclasses import replace

import pytest
from test_app import FakePlayer, populated

from kirlian_terminal.animations import (
    CATALOG,
    HEIGHT,
    WIDTH,
    AnimationClock,
    PatternDeck,
    Variation,
)
from kirlian_terminal.app import KirlianApp, PlayerUpdate
from kirlian_terminal.patterns import FAMILIES
from kirlian_terminal.playback import PlaybackState
from kirlian_terminal.visuals import Animation


def test_catalog_has_one_hundred_named_stable_patterns():
    assert len(CATALOG) == len(set(CATALOG)) == 100
    assert len({v.label for v in CATALOG}) == 100
    for family in FAMILIES:
        assert len([v for v in CATALOG if v.family == family]) == 10
    for variation in CATALOG:
        assert variation.version == 2
        assert Variation.parse(variation.code) == variation


@pytest.mark.parametrize(
    "code",
    ["v3:filaments:0", "v2:filaments:a", "v2:seeds:-1", "v2:unknown:0", "v1:seeds:0", "invalid"],
)
def test_unknown_catalog_versions_and_patterns_are_rejected(code):
    with pytest.raises(ValueError):
        Variation.parse(code)


@pytest.mark.parametrize("characters", ["dots", "ascii"])
@pytest.mark.parametrize("width", [1, 24, 76, 156, 400, 10000])
def test_catalog_frames_are_bounded_deterministic_and_distinct(width, characters):
    frames = set()
    for variation in CATALOG:
        frame = variation.ribbon_frame(3, width, characters)
        assert frame == variation.ribbon_frame(3, width, characters)
        lines = frame.splitlines()
        assert len(lines) == HEIGHT
        assert all(len(line) == min(400, width) for line in lines)
        if characters == "ascii":
            assert all(32 <= ord(c) <= 126 for c in frame if c != "\n")
        else:
            assert all(0x2800 <= ord(c) <= 0x28FF for c in frame if c != "\n")
        if width >= 76:
            assert frame != variation.ribbon_frame(19, width, characters), variation.label
        frames.add(frame)
    if width >= 76:
        assert len(frames) == 100


@pytest.mark.parametrize(
    "family,characters,digest",
    [
        ("filaments", "dots", "4648661d2a4f219ecd753392944ac90327b07268d1aa1384fa48ab991f76eb43"),
        ("filaments", "ascii", "217aba26b57733a22dde0b051c4c50f4ebcfe284ee0447a02886a9153fea2235"),
        ("ripples", "dots", "bc2c49c6b8150a62d9fdedf913c8b438d84be78888de4cc55bf474d2e75d2c5d"),
        ("ripples", "ascii", "22b4ff593bac656325c08422c2d3ef60fc96f87a074d465becc3294badb461e2"),
    ],
)
def test_pre_catalog_saved_ribbons_keep_their_exact_drawing(family, characters, digest):
    variation = Variation.parse(f"v1:{family}:00000011")
    assert hashlib.sha256(variation.ribbon_frame(3, 76, characters).encode()).hexdigest() == digest


def test_shuffle_uses_whole_catalog_and_does_not_repeat_at_cycle_boundary():
    clock = AnimationClock()
    seen = [clock.variation]
    for index in range(99):
        before = clock.variation
        clock.shuffle(index)
        assert clock.variation != before
        seen.append(clock.variation)
    assert set(seen) == set(CATALOG)
    seen = []
    for index in range(100):
        before = clock.variation
        clock.shuffle(index)
        assert clock.variation != before
        seen.append(clock.variation)
    assert set(seen) == set(CATALOG)


def test_recalling_last_available_pattern_does_not_break_shuffle():
    variation = CATALOG[0]
    deck = PatternDeck([variation])
    assert deck.next(variation) != variation


@pytest.mark.parametrize("family", ["filaments", "ripples"])
def test_frames_are_fixed_size_ascii_deterministic_and_varied(family):
    frames = set()
    for seed in range(64):
        variation = Variation(family, seed)
        assert Variation.parse(variation.code) == variation
        frame = variation.frame(2.5)
        assert frame == variation.frame(2.5)
        assert len(frame.splitlines()) == HEIGHT
        assert all(len(line) == WIDTH for line in frame.splitlines())
        assert all(32 <= ord(c) < 127 for c in frame if c != "\n")
        assert frame != variation.frame(12.5)
        frames.add(frame)
    assert len(frames) > 55


def test_pause_freezes_clock_and_new_file_chooses_new_variation():
    clock = AnimationClock()
    clock.observe(1, True, 10)
    selected = clock.variation
    clock.observe(1, False, 12)
    assert clock.time(1000) == 2
    clock.observe(1, True, 1000)
    assert clock.time(1003) == 5
    assert clock.variation == selected
    clock.observe(2, True, 1004)
    assert clock.variation != selected
    assert clock.time(1004) == 0


async def test_motion_controls_pause_seek_disable_save_and_recall(tmp_path, audio_factory):
    library, paths = populated(tmp_path, audio_factory)
    player = FakePlayer()
    app = KirlianApp(library, player=player)
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        animation = app.query_one(Animation)
        state = PlaybackState(paused=False, idle=False, started_serial=1, path=paths[0])
        app.on_player_update(PlayerUpdate(state))
        await pilot.pause(0.15)
        original = animation.clock.variation
        assert original in CATALOG
        assert animation.timer is not None
        region = animation.region
        app.on_player_update(PlayerUpdate(replace(state, position=150)))
        assert animation.clock.variation == original
        app.on_player_update(PlayerUpdate(replace(state, paused=True)))
        frozen = animation.render().plain
        await pilot.pause(0.2)
        assert animation.timer is None
        assert animation.render().plain == frozen
        await pilot.press("s", "x")
        assert animation.clock.variation != original
        await pilot.press("S")
        assert animation.clock.variation == original
        await pilot.press("v")
        assert not animation.enabled and animation.timer is None
        assert animation.render().plain == ""
        assert region == animation.region
        await pilot.press("slash", "x", "v", "s", "S")
        assert not animation.enabled
        assert animation.clock.variation == original
        assert not player.calls
    other = KirlianApp(library, player=FakePlayer())
    async with other.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        animation = other.query_one(Animation)
        assert not animation.enabled
        await pilot.press("S")
        assert animation.clock.variation == original


@pytest.mark.parametrize("width", [1, 40, 76, 156, 400])
@pytest.mark.parametrize("characters", ["dots", "ascii"])
def test_ribbon_is_bounded_deterministic_and_changes_with_time(width, characters):
    variation = Variation("filaments", 17)
    frame = variation.ribbon_frame(3, width, characters)
    assert len(frame.splitlines()) == 3
    assert all(len(line) == width for line in frame.splitlines())
    assert frame == variation.ribbon_frame(3, width, characters)
    if width > 1:
        assert frame != variation.ribbon_frame(11, width, characters)
    if characters == "ascii":
        assert frame.isascii()
    else:
        assert all(0x2800 <= ord(c) <= 0x28FF for c in frame if c != "\n")


def test_title_rhythm_hits_syllables_rests_between_words_and_stays_bounded():
    from kirlian_terminal.visuals import ACCENT, REST, WEAK, rhythm

    # Pa-ris: accent + weak; each digit of 1919 is its own hit.
    assert rhythm("Paris 1919") == [ACCENT, WEAK, REST, ACCENT, WEAK, WEAK, WEAK, REST]
    # Vowel groups count once; a vowel-less word still lands one hit.
    assert rhythm("Queen's Rhythm") == [ACCENT, REST, ACCENT, REST]
    assert len(rhythm("a " * 40)) == 16
    assert rhythm("") == rhythm("—") == [ACCENT, REST, WEAK, REST]
