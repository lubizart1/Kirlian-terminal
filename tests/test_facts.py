import io
import json
import urllib.error

import keyring
import pytest
from keyring.errors import KeyringError

from kirlian_terminal import facts
from kirlian_terminal.facts import PROVIDERS, Credentials, FactsError, request_facts
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
    assert fact.source_label == "John Cale on Paris 1919, 2010"


def test_unusable_answers_and_non_web_sources():
    local = {"headline": "H", "body": "B", "source_url": "file:///etc/passwd"}
    assert facts.verified_facts({"facts": [local]}, [facts.source("file:///etc/passwd")]) == []
    assert facts.verified_facts("not json", [facts.source(URL)]) == []
    assert facts.verified_facts({"facts": "nope"}, []) == []


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
