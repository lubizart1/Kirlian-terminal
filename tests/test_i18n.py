# SPDX-License-Identifier: GPL-3.0-or-later
import sys
from pathlib import Path

import pytest

from kirlian_terminal import i18n
from kirlian_terminal.i18n import LANGUAGES, _, n_, resolve, set_language, system_language

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from i18n_catalog import extract, fields, problems  # noqa: E402


@pytest.fixture(autouse=True)
def english_afterwards():
    yield
    set_language("en")


@pytest.mark.parametrize(
    ("environ", "expected"),
    [
        ({"LANG": "es_MX.UTF-8"}, "es"),
        ({"LANG": "pt_PT.UTF-8"}, "pt-BR"),
        ({"LANG": "zh_CN.UTF-8"}, "zh-Hans"),
        ({"LANG": "zh_TW.UTF-8"}, "en"),  # Traditional Chinese is not translated.
        ({"LC_ALL": "ja_JP.UTF-8", "LANG": "de_DE.UTF-8"}, "ja"),
        ({"LC_MESSAGES": "fr_FR", "LANG": "de_DE"}, "fr"),
        ({"LANG": "C.UTF-8"}, "en"),
        ({"LANG": "sv_SE.UTF-8"}, "en"),
        ({}, "en"),
    ],
)
def test_system_language_follows_locale_precedence(environ, expected):
    assert system_language(environ) == expected


def test_saved_choice_wins_over_the_locale():
    assert resolve("ko", {"LANG": "de_DE"}) == "ko"
    assert resolve("auto", {"LANG": "de_DE"}) == "de"
    assert resolve("klingon", {"LANG": "it_IT"}) == "it"


def test_missing_entries_fall_back_to_english_and_values_are_inserted(monkeypatch):
    set_language("de")
    monkeypatch.setattr(i18n, "_catalog", {"Hello {name}": "Hallo {name}"})
    assert _("Hello {name}", name="Air") == "Hallo Air"
    assert _("Not translated {x}", x=1) == "Not translated 1"


def test_plural_rules_per_language(monkeypatch):
    entry = {"{n} song": {"one": "{n} chanson", "other": "{n} chansons"}}
    set_language("fr")
    monkeypatch.setattr(i18n, "_catalog", entry)
    assert n_("{n} song", "{n} songs", 0) == "0 chanson"
    assert n_("{n} song", "{n} songs", 2) == "2 chansons"
    set_language("ja")
    monkeypatch.setattr(i18n, "_catalog", {"{n} song": {"one": "x", "other": "{n} 曲"}})
    assert n_("{n} song", "{n} songs", 1) == "1 曲"
    set_language("en")
    assert n_("{n} song", "{n} songs", 1) == "1 song"
    assert n_("{n} song", "{n} songs", 3) == "3 songs"


def test_sources_are_extractable_literals():
    sources = extract()
    assert len(sources) > 100
    assert all(source.strip() for source in sources)


@pytest.mark.parametrize("code", [code for code in LANGUAGES if code != "en"])
def test_every_catalog_is_complete_and_keeps_placeholders(code):
    """A missing placeholder would raise at runtime; a stale entry is dead weight."""
    assert problems(code) == []


@pytest.mark.parametrize("code", [code for code in LANGUAGES if code != "en"])
def test_every_translation_formats_with_its_values(code):
    set_language(code)
    for source, info in extract().items():
        values = {name: "X" for name in fields(source) if name != "n"}
        if info["plural"]:
            for count in (0, 1, 2, 5):
                assert n_(source, info["plural"], count, **values)
        else:
            assert _(source, **values)


async def test_saved_language_translates_the_interface_and_changes_apply_on_relaunch(
    tmp_path, audio_factory
):
    import json

    from test_app import FakePlayer, populated
    from textual.widgets import OptionList, Select

    from kirlian_terminal.app import KirlianApp
    from kirlian_terminal.appearance import Appearance

    library, _paths = populated(tmp_path, audio_factory)
    library.set_setting("appearance", json.dumps({"language": "es"}))
    player = FakePlayer()
    app = KirlianApp(library, player=player)
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        nav = app.query_one("#nav", OptionList)
        assert str(nav.get_option_at_index(0).prompt) == "Álbumes"
        await pilot.press("p")
        app.query_one("#pref-language", Select).value = "ja"
        await pilot.pause()
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert Appearance.load(library).language == "ja"
        # The running interface stays Spanish; the change is announced instead.
        assert str(nav.get_option_at_index(0).prompt) == "Álbumes"
        saved = _("Language saved. It applies the next time you open Kirlian.")
        assert saved.startswith("Idioma")
        assert str(app.query_one("#status").content) == saved
        assert not player.calls

    relaunched = KirlianApp(library, player=FakePlayer())
    async with relaunched.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        prompt = str(relaunched.query_one("#nav", OptionList).get_option_at_index(0).prompt)
        assert prompt == "アルバム"


def test_notes_are_requested_and_cached_per_language(tmp_path):
    from kirlian_terminal.facts import FactCache, question
    from kirlian_terminal.library import Library, Track

    track = Track("", "Paris 1919", "John Cale", "Paris 1919", "John Cale", "", 1, 6, 0, "1973", "")
    assert "Write the headlines" not in question(track)
    cache = FactCache(Library(tmp_path / "library.db"))
    english = cache.key("exa", "song")
    set_language("fr")
    assert "in French" in question(track)
    assert cache.key("exa", "song") != english
