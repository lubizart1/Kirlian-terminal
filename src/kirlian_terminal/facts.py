"""Optional sourced song facts from Exa. Only artist, album, title, and year leave the machine."""

from __future__ import annotations

import contextlib
import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from urllib.parse import urlsplit

import keyring
from keyring.errors import KeyringError

from .library import Library, Track, display_text

ENDPOINT = "https://api.exa.ai/answer"
KEY_ENVIRONMENT = "EXA_API_KEY"
KEYRING_SERVICE = "kirlian-terminal"
KEYRING_USER = "exa"
TIMEOUT = 25
HEADLINE_LIMIT = 60
BODY_LIMIT = 280

SCHEMA = {
    "type": "object",
    "properties": {
        "facts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "headline": {"type": "string"},
                    "body": {"type": "string"},
                    "source_url": {"type": "string"},
                },
                "required": ["headline", "body", "source_url"],
            },
        }
    },
    "required": ["facts"],
}


class FactsError(Exception):
    """A readable reason the provider gave no facts."""


@dataclass(frozen=True)
class Fact:
    headline: str
    body: str
    source_title: str
    source_url: str
    published: str = ""

    @property
    def source_label(self) -> str:
        year = self.published[:4]
        return f"{self.source_title}, {year}" if year.isdigit() else self.source_title


def fact_key(track: Track) -> str:
    return "\x1f".join(value.casefold() for value in (track.artist, track.album, track.title))


def question(track: Track) -> str:
    year = f", {track.year}" if track.year else ""
    return (
        f'Find up to three short, specific facts about how the song "{track.title}" by '
        f'{track.artist} (from the album "{track.album}"{year}) was written or recorded: '
        "the people who played on it, the studio, the process, or the story behind it. "
        "Each fact needs a headline under 8 words and a body under 45 words, written for a "
        "listener. Use only what a cited source states and give that source's URL. Skip "
        "generic praise, chart positions, and anything about a different song. Return no "
        "facts rather than guessing."
    )


def same_page(left: str, right: str) -> bool:
    def normal(url: str) -> tuple[str, str, str]:
        parts = urlsplit(url.strip())
        host = parts.netloc.casefold().removeprefix("www.")
        return host, parts.path.rstrip("/"), parts.query

    return normal(left) == normal(right)


def clip(text: str, limit: int) -> str:
    text = display_text(text)
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def parse_response(payload: dict) -> list[Fact]:
    """Keep facts whose URL matches a page Exa actually retrieved and cited."""
    answer = payload.get("answer")
    if isinstance(answer, str):
        try:
            answer = json.loads(answer)
        except ValueError:
            return []
    if not isinstance(answer, dict) or not isinstance(answer.get("facts"), list):
        return []
    citations = [c for c in payload.get("citations") or [] if isinstance(c, dict)]
    facts: list[Fact] = []
    for item in answer["facts"]:
        if not isinstance(item, dict):
            continue
        headline = clip(str(item.get("headline") or ""), HEADLINE_LIMIT)
        body = clip(str(item.get("body") or ""), BODY_LIMIT)
        url = str(item.get("source_url") or "")
        source = next(
            (c for c in citations if c.get("url") and same_page(str(c["url"]), url)), None
        )
        if not headline or not body or source is None:
            continue
        source_url = str(source["url"])
        if urlsplit(source_url).scheme not in {"http", "https"}:
            continue
        title = clip(str(source.get("title") or urlsplit(source_url).netloc), 70)
        facts.append(
            Fact(headline, body, title, source_url, str(source.get("publishedDate") or ""))
        )
    return facts[:3]


def request_facts(track: Track, key: str, timeout: float = TIMEOUT) -> list[Fact]:
    """Blocking; run off the UI loop."""
    body = json.dumps({"query": question(track), "outputSchema": SCHEMA}).encode()
    request = urllib.request.Request(
        ENDPOINT,
        data=body,
        headers={"x-api-key": key, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as error:
        if error.code in {401, 403}:
            raise FactsError("Exa rejected the API key. Press i to replace it.") from None
        if error.code == 429:
            raise FactsError("Exa rate limit or credits reached; facts paused.") from None
        raise FactsError(f"Exa returned HTTP {error.code}; no fact for this song.") from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise FactsError("Could not reach Exa; no fact for this song.") from None
    except ValueError:
        raise FactsError("Exa sent an unreadable response.") from None
    return parse_response(payload) if isinstance(payload, dict) else []


class Credentials:
    """Environment first, then the OS credential store, then a session-only key."""

    def __init__(self) -> None:
        self.session = ""

    def key(self) -> str:
        if value := os.environ.get(KEY_ENVIRONMENT, "").strip():
            return value
        if self.session:
            return self.session
        try:
            return keyring.get_password(KEYRING_SERVICE, KEYRING_USER) or ""
        except KeyringError:
            return ""

    def source(self) -> str:
        if os.environ.get(KEY_ENVIRONMENT, "").strip():
            return "environment"
        if self.session:
            return "session"
        return "keychain" if self.key() else ""

    def save(self, value: str, remember: bool) -> bool:
        """False when the credential store is unavailable; the key then lasts this session."""
        self.session = ""
        if remember:
            try:
                keyring.set_password(KEYRING_SERVICE, KEYRING_USER, value)
                return True
            except KeyringError:
                pass
        self.session = value
        return not remember

    def forget(self) -> None:
        self.session = ""
        with contextlib.suppress(KeyringError):
            keyring.delete_password(KEYRING_SERVICE, KEYRING_USER)


class FactCache:
    """Facts per song, kept so each song is requested once, not once per launch."""

    def __init__(self, library: Library) -> None:
        self.library = library
        with library.connect() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS facts (key TEXT PRIMARY KEY, facts TEXT NOT NULL)"
            )

    def get(self, key: str) -> list[Fact] | None:
        with self.library.connect() as db:
            row = db.execute("SELECT facts FROM facts WHERE key = ?", (key,)).fetchone()
        if row is None:
            return None
        try:
            return [Fact(**item) for item in json.loads(row[0])]
        except (ValueError, TypeError):
            return None

    def put(self, key: str, facts: list[Fact]) -> None:
        with self.library.connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO facts VALUES (?, ?)",
                (key, json.dumps([vars(fact) for fact in facts])),
            )
