# SPDX-License-Identifier: GPL-3.0-or-later
import io
import json
import urllib.error

import keyring
import pytest
from keyring.errors import KeyringError

from kirlian_terminal import facts
from kirlian_terminal.facts import (
    PROVIDERS,
    Credentials,
    FactsConfig,
    FactsError,
    request_facts,
)
from kirlian_terminal.library import Track

TRACK = Track(
    path="/private/music/06 Paris 1919.flac",
    title="Paris 1919",
    artist="John Cale",
    album="Paris 1919",
    album_artist="John Cale",
    album_id="a",
    disc=1,
    track=6,
    duration=200,
    year="1973",
    format="FLAC",
)
URL = "https://www.example.org/cale-interview/"
SAMPLE = ("John Cale", "Paris 1919", "Paris 1919", "1973")
GOOD = {
    "headline": "Little Feat in the room",
    "body": "Lowell George\x1b[31m played on the album.",
    "source_url": "http://example.org/cale-interview",
}
INVENTED = {"headline": "Invented", "body": "No source.", "source_url": "https://made.up/page"}
ANSWER = {"facts": [GOOD, INVENTED]}

# Minimal responses in each provider's documented shape.
PAYLOADS = {
    "exa": {
        "answer": ANSWER,
        "citations": [
            {"url": URL, "title": "John Cale on Paris 1919", "publishedDate": "2010-05-01"}
        ],
    },
    "openai": {
        "output": [
            {
                "type": "web_search_call",
                "action": {"type": "search", "sources": [{"type": "url", "url": URL}]},
            },
            {
                "type": "message",
                "content": [
                    {
                        "type": "output_text",
                        "text": json.dumps(ANSWER),
                        "annotations": [
                            {"type": "url_citation", "url": URL, "title": "John Cale on Paris 1919"}
                        ],
                    }
                ],
            },
        ]
    },
    "parallel": {
        "output": [
            {"type": "web_search_call", "action": {"type": "open_page", "url": URL}},
            {
                "type": "message",
                "content": [{"type": "output_text", "text": json.dumps(ANSWER), "annotations": []}],
            },
        ]
    },
    "perplexity": {
        "output": [
            {
                "type": "search_results",
                "results": [
                    {"id": 1, "url": URL, "title": "John Cale on Paris 1919", "date": "2010-05-01"}
                ],
            },
            {
                "type": "message",
                "content": [{"type": "output_text", "text": json.dumps(ANSWER)}],
            },
        ]
    },
    "anthropic": {
        "content": [
            {"type": "text", "text": "I'll search for this."},
            {"type": "server_tool_use", "name": "web_search"},
            {
                "type": "web_search_tool_result",
                "content": [
                    {
                        "type": "web_search_result",
                        "url": URL,
                        "title": "John Cale on Paris 1919",
                        "page_age": "2010-05-01",
                    }
                ],
            },
            {"type": "text", "text": f"```json\n{json.dumps(ANSWER)}\n```"},
        ]
    },
}


@pytest.mark.parametrize("provider_id", sorted(PAYLOADS))
def test_each_provider_keeps_only_facts_from_retrieved_pages(provider_id, monkeypatch):
    sent = {}

    def fake_urlopen(request, timeout):
        sent["url"] = request.full_url
        sent["headers"] = {k.casefold(): v for k, v in request.header_items()}
        sent["body"] = json.loads(request.data)
        return io.BytesIO(json.dumps(PAYLOADS[provider_id]).encode())

    monkeypatch.setattr(facts.urllib.request, "urlopen", fake_urlopen)
    provider = PROVIDERS[provider_id]
    [fact] = request_facts(provider, TRACK, "secret")

    assert fact.headline == "Little Feat in the room"
    assert "\x1b" not in fact.body
    assert fact.source_url == URL
    assert fact.source_title in {"John Cale on Paris 1919", "www.example.org"}
    assert sent["url"] == provider.endpoint
    assert "secret" in " ".join(sent["headers"].values())
    assert "/private/music" not in json.dumps(sent["body"])
    assert "John Cale" in json.dumps(sent["body"])


def test_titles_and_dates_merge_across_duplicate_source_entries():
    [fact] = facts.verified_facts(
        ANSWER, [facts.source(URL), facts.source(URL, "John Cale on Paris 1919", "2010-05-01")]
    )
    assert fact.source_label == "John Cale on Paris 1919 · example.org, 2010"


def test_unusable_answers_and_non_web_sources():
    local = {"headline": "H", "body": "B", "source_url": "file:///etc/passwd"}
    assert facts.verified_facts({"facts": [local]}, [facts.source("file:///etc/passwd")]) == []
    assert facts.verified_facts("not json", [facts.source(URL)]) == []
    assert facts.verified_facts({"facts": "nope"}, []) == []


def test_hostile_source_urls_are_dropped_not_raised():
    escape = {"headline": "H", "body": "B", "source_url": URL + "\x1b]52;c;eA==\x07"}
    broken = {"headline": "H", "body": "B", "source_url": "https://[x"}
    assert facts.verified_facts({"facts": [escape, broken]}, [facts.source(URL)]) == []
    # Nesting deep enough to exhaust the JSON parser's recursion is just unreadable.
    assert facts.verified_facts("{" + "[" * 100_000 + "}", [facts.source(URL)]) == []


def test_errors_name_the_provider(monkeypatch):
    def rejected(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 401, "no", {}, None)

    monkeypatch.setattr(facts.urllib.request, "urlopen", rejected)
    with pytest.raises(FactsError, match="OpenAI rejected the API key"):
        request_facts(PROVIDERS["openai"], TRACK, "bad")

    def slow(request, timeout):
        raise TimeoutError

    monkeypatch.setattr(facts.urllib.request, "urlopen", slow)
    with pytest.raises(FactsError, match="Could not reach Parallel"):
        request_facts(PROVIDERS["parallel"], TRACK, "key")


def test_credentials_are_per_provider_with_environment_and_session_fallbacks(monkeypatch):
    exa, openai = PROVIDERS["exa"], PROVIDERS["openai"]
    for provider in PROVIDERS.values():
        monkeypatch.delenv(provider.environment, raising=False)
    credentials = Credentials()
    assert credentials.save(exa, "exa-key", remember=True)
    assert (credentials.key(exa), credentials.source(exa)) == ("exa-key", "keychain")
    assert credentials.key(openai) == ""

    monkeypatch.setenv("OPENAI_API_KEY", "from-env")
    assert (credentials.key(openai), credentials.source(openai)) == ("from-env", "environment")
    monkeypatch.delenv("OPENAI_API_KEY")

    def unavailable(*args):
        raise KeyringError("no backend")

    monkeypatch.setattr(keyring, "set_password", unavailable)
    assert not credentials.save(openai, "temporary", remember=True)
    assert (credentials.key(openai), credentials.source(openai)) == ("temporary", "session")
    credentials.forget(openai)
    assert credentials.key(openai) == ""
    assert credentials.key(exa) == "exa-key"


def test_live_check_explains_kept_and_dropped_facts_without_revealing_the_key(
    tmp_path, monkeypatch
):
    from kirlian_terminal.facts_check import run_facts_check

    monkeypatch.setenv("PERPLEXITY_API_KEY", "sk-secret-value")
    monkeypatch.setattr(
        facts.urllib.request,
        "urlopen",
        lambda request, timeout: io.BytesIO(json.dumps(PAYLOADS["perplexity"]).encode()),
    )
    out = io.StringIO()
    report = tmp_path / "report.json"
    assert run_facts_check("perplexity", FactsConfig(), SAMPLE, report, out) == 0
    text = out.getvalue()
    assert "Notes proposed: 2 · shown after the source check: 1" in text
    assert "✓ [story] Little Feat in the room" in text
    assert "✗ Invented" in text
    assert "sk-secret-value" not in text + report.read_text()
    assert json.loads(report.read_text())["results"][0]["retrieved_pages"] == [URL]

    def rejected(request, timeout):
        raise urllib.error.HTTPError(
            request.full_url, 400, "bad", {}, io.BytesIO(b'{"error": "unknown model"}')
        )

    monkeypatch.setattr(facts.urllib.request, "urlopen", rejected)
    out = io.StringIO()
    assert run_facts_check("perplexity", FactsConfig(), SAMPLE, None, out) == 1
    assert "unknown model" in out.getvalue()


def test_readings_keep_their_kind_and_the_answering_provider(monkeypatch):
    reading = {**GOOD, "kind": "reading"}
    payload = {**PAYLOADS["exa"], "answer": {"facts": [reading, {**GOOD, "kind": "rumor"}]}}
    monkeypatch.setattr(
        facts.urllib.request, "urlopen", lambda r, timeout: io.BytesIO(json.dumps(payload).encode())
    )
    first, second = request_facts(PROVIDERS["exa"], TRACK, "key")
    assert (first.kind, first.provider) == ("reading", "Exa")
    assert second.kind == "story"  # Unknown kinds are not shown as interpretation.


def test_facts_config_migrates_the_single_provider_setting_and_ignores_bad_values(tmp_path):
    from kirlian_terminal.library import Library

    library = Library(tmp_path / "library.db")
    library.set_setting("facts_provider", "perplexity")
    assert FactsConfig.load(library).order == ["perplexity"]
    library.set_setting(
        "facts_config",
        json.dumps(
            {"order": ["openai", "nope", "openai", "exa"], "models": {"exa": "x", "openai": "m"}}
        ),
    )
    config = FactsConfig.load(library)
    assert config.order == ["openai", "exa"]
    assert config.models == {"openai": "m"}  # Exa has no model choice.
    assert config.model(PROVIDERS["anthropic"]) == PROVIDERS["anthropic"].model


def test_a_song_already_paid_for_is_never_asked_again(tmp_path):
    from kirlian_terminal.facts import PROMPT_VERSION, Fact, FactCache
    from kirlian_terminal.library import Library

    library = Library(tmp_path / "library.db")
    song = "artist\x1falbum\x1fsong_100%"  # SQL wildcards in a title match only literally.
    older = Fact("Older prompt", "B", "T", "https://e.org/old")
    with library.connect() as db:
        db.execute("CREATE TABLE facts (key TEXT PRIMARY KEY, facts TEXT NOT NULL)")
        # Saved by an earlier release whose prompt has since changed.
        key = f"v{int(PROMPT_VERSION) - 1}\x1fperplexity\x1f{song}"
        db.execute("INSERT INTO facts VALUES (?, ?)", (key, json.dumps([vars(older)])))
        db.execute("INSERT INTO facts VALUES ('artist\x1falbum\x1fsong_1000', '[]')")
    cache = FactCache(library)
    assert cache.saved(song, "en", ["openai"]) == [older]  # Survives upgrades and reordering.
    assert cache.saved("artist\x1falbum\x1fother", "en", ["openai"]) is None
    assert cache.saved(song, "fr", ["openai"]) is None  # Another language is a new request.

    cache.put("exa", song, [])  # "Nothing found" is saved too, but notes win.
    current = Fact("Current", "B", "T", "https://e.org/new")
    cache.put("anthropic", song, [current])
    assert cache.saved(song, "en", ["exa", "openai"]) == [current]
    cache.put("openai", song, [Fact("Primary", "B", "T", "https://e.org/p")])
    assert cache.saved(song, "en", ["openai", "anthropic"])[0].headline == "Primary"


def test_a_dropped_connection_is_sent_once_more_and_then_explained(monkeypatch):
    import http.client

    attempts = []

    def drop_then_answer(request, timeout):
        attempts.append(1)
        if len(attempts) == 1:
            raise http.client.RemoteDisconnected("closed")
        return io.BytesIO(json.dumps(PAYLOADS["perplexity"]).encode())

    monkeypatch.setattr(facts.urllib.request, "urlopen", drop_then_answer)
    assert request_facts(PROVIDERS["perplexity"], TRACK, "key")
    assert len(attempts) == 2

    def always_drop(request, timeout):
        attempts.append(1)
        raise ConnectionResetError("reset")

    attempts.clear()
    monkeypatch.setattr(facts.urllib.request, "urlopen", always_drop)
    with pytest.raises(
        FactsError, match=r"Could not reach Perplexity \(connection dropped\)"
    ) as raised:
        request_facts(PROVIDERS["perplexity"], TRACK, "key")
    assert raised.value.transient and len(attempts) == 2

    def slow(request, timeout):
        attempts.append(1)
        raise TimeoutError

    attempts.clear()
    monkeypatch.setattr(facts.urllib.request, "urlopen", slow)
    with pytest.raises(FactsError, match="timed out"):
        request_facts(PROVIDERS["perplexity"], TRACK, "key")
    assert len(attempts) == 1  # A 90-second wait is not repeated.
