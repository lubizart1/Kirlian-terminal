import io
import json
import urllib.error

import keyring
import pytest
from keyring.errors import KeyringError

from kirlian_terminal import facts
from kirlian_terminal.facts import Credentials, FactsError, parse_response, request_facts
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

CITATIONS = [
    {
        "title": "John Cale on Paris 1919",
        "url": "https://www.example.org/cale-interview/",
        "publishedDate": "2010-05-01T00:00:00.000Z",
    }
]


def answer(*items):
    return {"answer": {"facts": list(items)}, "citations": CITATIONS}


def test_only_facts_backed_by_a_retrieved_citation_are_kept():
    payload = answer(
        {
            "headline": "Little Feat in the room",
            "body": "Lowell George\x1b[31m played on the album.",
            "source_url": "http://example.org/cale-interview",
        },
        {"headline": "Invented", "body": "No source.", "source_url": "https://made.up/page"},
        {"headline": "", "body": "Missing headline.", "source_url": CITATIONS[0]["url"]},
    )
    [fact] = parse_response(payload)
    assert fact.headline == "Little Feat in the room"
    assert "\x1b" not in fact.body
    assert fact.source_url == CITATIONS[0]["url"]
    assert fact.source_label == "John Cale on Paris 1919, 2010"


def test_string_answers_and_non_web_sources():
    item = {"headline": "H", "body": "B", "source_url": "file:///etc/passwd"}
    payload = {
        "answer": json.dumps({"facts": [item]}),
        "citations": [{"title": "Local", "url": "file:///etc/passwd"}],
    }
    assert parse_response(payload) == []
    assert parse_response({"answer": "not json", "citations": CITATIONS}) == []
    assert parse_response({"answer": {"facts": "nope"}}) == []


def test_request_sends_metadata_only_and_maps_errors(monkeypatch):
    sent = {}

    def fake_urlopen(request, timeout):
        sent["body"] = json.loads(request.data)
        sent["key"] = request.get_header("X-api-key")
        return io.BytesIO(json.dumps(answer()).encode())

    monkeypatch.setattr(facts.urllib.request, "urlopen", fake_urlopen)
    assert request_facts(TRACK, "secret") == []
    assert sent["key"] == "secret"
    assert "/private/music" not in json.dumps(sent["body"])
    assert "John Cale" in sent["body"]["query"]

    def rejected(request, timeout):
        raise urllib.error.HTTPError(facts.ENDPOINT, 401, "no", {}, None)

    monkeypatch.setattr(facts.urllib.request, "urlopen", rejected)
    with pytest.raises(FactsError, match="rejected the API key"):
        request_facts(TRACK, "bad")

    def slow(request, timeout):
        raise TimeoutError

    monkeypatch.setattr(facts.urllib.request, "urlopen", slow)
    with pytest.raises(FactsError, match="Could not reach Exa"):
        request_facts(TRACK, "key")


def test_credentials_prefer_environment_and_fall_back_to_session(monkeypatch):
    monkeypatch.delenv(facts.KEY_ENVIRONMENT, raising=False)
    credentials = Credentials()
    assert credentials.save("stored", remember=True)
    assert (credentials.key(), credentials.source()) == ("stored", "keychain")

    monkeypatch.setenv(facts.KEY_ENVIRONMENT, "from-env")
    assert (credentials.key(), credentials.source()) == ("from-env", "environment")
    monkeypatch.delenv(facts.KEY_ENVIRONMENT)

    def unavailable(*args):
        raise KeyringError("no backend")

    monkeypatch.setattr(keyring, "set_password", unavailable)
    assert not credentials.save("temporary", remember=True)
    assert (credentials.key(), credentials.source()) == ("temporary", "session")
    credentials.forget()
    assert credentials.key() == ""
