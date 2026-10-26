"""Optional sourced song facts. Only title, artist, album, and year leave the machine.

Each provider is asked the same question and returns facts with a source URL plus
the pages its search actually retrieved. A fact is kept only when its URL matches
one of those retrieved pages, whichever provider answered.
"""

from __future__ import annotations

import contextlib
import json
import os
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urlsplit

import keyring
from keyring.errors import KeyringError

from .library import Library, Track, display_text

KEYRING_SERVICE = "kirlian-terminal"
MODEL_ENVIRONMENT = "KIRLIAN_FACTS_MODEL"
TIMEOUT = 60
HEADLINE_LIMIT = 60
BODY_LIMIT = 280

FACT = {
    "type": "object",
    "properties": {
        "headline": {"type": "string"},
        "body": {"type": "string"},
        "source_url": {"type": "string"},
    },
    "required": ["headline", "body", "source_url"],
}
SCHEMA = {
    "type": "object",
    "properties": {"facts": {"type": "array", "items": FACT}},
    "required": ["facts"],
}
# OpenAI-style strict schemas also forbid undeclared properties.
STRICT_SCHEMA = {
    **SCHEMA,
    "additionalProperties": False,
    "properties": {"facts": {"type": "array", "items": {**FACT, "additionalProperties": False}}},
}

Source = dict[str, str]  # url, title, published


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
        f'Search the web for up to three short, specific facts about how the song "{track.title}" '
        f'by {track.artist} (from the album "{track.album}"{year}) was written or recorded: '
        "the people who played on it, the studio, the process, or the story behind it. "
        "Each fact needs a headline under 8 words and a body under 45 words, written for a "
        "listener. Use only what a source you found states, and give that page's exact URL. "
        "Skip generic praise, chart positions, and anything about a different song. Return no "
        'facts rather than guessing. Reply with only JSON: {"facts": [{"headline": "...", '
        '"body": "...", "source_url": "https://..."}]}'
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


def json_object(answer: object) -> dict | None:
    """Accept a decoded object, JSON text, or JSON wrapped in prose or a code fence."""
    if isinstance(answer, dict):
        return answer
    if not isinstance(answer, str):
        return None
    start, end = answer.find("{"), answer.rfind("}")
    if start < 0 or end < start:
        return None
    try:
        value = json.loads(answer[start : end + 1])
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


def verified_facts(answer: object, sources: list[Source]) -> list[Fact]:
    """Keep facts whose URL matches a page the provider's search actually retrieved."""
    answer = json_object(answer)
    if answer is None or not isinstance(answer.get("facts"), list):
        return []
    facts: list[Fact] = []
    for item in answer["facts"]:
        if not isinstance(item, dict):
            continue
        headline = clip(str(item.get("headline") or ""), HEADLINE_LIMIT)
        body = clip(str(item.get("body") or ""), BODY_LIMIT)
        url = str(item.get("source_url") or "")
        matches = [s for s in sources if s.get("url") and same_page(s["url"], url)]
        if not headline or not body or not matches:
            continue
        # The same page can be listed more than once; prefer an entry with a title.
        source = max(matches, key=lambda s: (bool(s.get("title")), bool(s.get("published"))))
        source_url = source["url"]
        if urlsplit(source_url).scheme not in {"http", "https"}:
            continue
        title = clip(source.get("title") or urlsplit(source_url).netloc, 70)
        facts.append(Fact(headline, body, title, source_url, source.get("published", "")))
    return facts[:3]


def source(url: object, title: object = "", published: object = "") -> Source:
    return {"url": str(url or ""), "title": str(title or ""), "published": str(published or "")}


def dicts(value: object) -> list[dict]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


# Response readers: each returns (answer, retrieved sources).


def read_exa(payload: dict) -> tuple[object, list[Source]]:
    citations = dicts(payload.get("citations"))
    return payload.get("answer"), [
        source(c.get("url"), c.get("title"), c.get("publishedDate")) for c in citations
    ]


def read_responses(payload: dict) -> tuple[object, list[Source]]:
    """OpenAI Responses shape, also used by Parallel and Perplexity's Agent API."""
    text: list[str] = []
    sources: list[Source] = []
    for item in dicts(payload.get("output")):
        kind = item.get("type")
        if kind == "message":
            for part in dicts(item.get("content")):
                if part.get("type") == "output_text":
                    text.append(str(part.get("text") or ""))
                    sources += [
                        source(a.get("url"), a.get("title"))
                        for a in dicts(part.get("annotations"))
                        if a.get("type") == "url_citation"
                    ]
        elif kind == "web_search_call" and isinstance(item.get("action"), dict):
            action = item["action"]
            sources += [source(s.get("url"), s.get("title")) for s in dicts(action.get("sources"))]
            if action.get("url"):
                sources.append(source(action["url"]))
        elif kind == "search_results":
            sources += [
                source(r.get("url"), r.get("title"), r.get("date"))
                for r in dicts(item.get("results"))
            ]
    return "".join(text), sources


def read_anthropic(payload: dict) -> tuple[object, list[Source]]:
    text: list[str] = []
    sources: list[Source] = []
    for block in dicts(payload.get("content")):
        if block.get("type") == "web_search_tool_result":
            sources += [
                source(r.get("url"), r.get("title"), r.get("page_age"))
                for r in dicts(block.get("content"))
                if r.get("type") == "web_search_result"
            ]
        elif block.get("type") == "text":
            text.append(str(block.get("text") or ""))
            sources += [source(c.get("url"), c.get("title")) for c in dicts(block.get("citations"))]
    # Claude may narrate before searching; the JSON answer is in the final text.
    return "".join(text[-1:]) if text else "", sources


def openai_style_format(strict: bool = False) -> dict:
    schema = {"type": "json_schema", "name": "song_facts", "schema": STRICT_SCHEMA}
    return {"format": schema | ({"strict": True} if strict else {})}


@dataclass(frozen=True)
class Provider:
    id: str
    name: str
    environment: str
    signup: str
    endpoint: str
    model: str
    body: Callable[[str, str], dict]
    read: Callable[[dict], tuple[object, list[Source]]]
    auth: str = "bearer"  # bearer, x-api-key, or anthropic

    def headers(self, key: str) -> dict[str, str]:
        if self.auth == "bearer":
            return {"Content-Type": "application/json", "Authorization": f"Bearer {key}"}
        headers = {"Content-Type": "application/json", "x-api-key": key}
        if self.auth == "anthropic":
            headers["anthropic-version"] = "2023-06-01"
        return headers


PROVIDERS: dict[str, Provider] = {
    provider.id: provider
    for provider in (
        Provider(
            "exa",
            "Exa",
            "EXA_API_KEY",
            "dashboard.exa.ai",
            "https://api.exa.ai/answer",
            "",
            lambda prompt, model: {"query": prompt, "outputSchema": SCHEMA},
            read_exa,
            auth="x-api-key",
        ),
        Provider(
            "openai",
            "OpenAI",
            "OPENAI_API_KEY",
            "platform.openai.com/api-keys",
            "https://api.openai.com/v1/responses",
            "gpt-5.4-mini",
            lambda prompt, model: {
                "model": model,
                "input": prompt,
                "tools": [{"type": "web_search"}],
                "include": ["web_search_call.action.sources"],
                "text": openai_style_format(strict=True),
            },
            read_responses,
        ),
        Provider(
            "anthropic",
            "Anthropic",
            "ANTHROPIC_API_KEY",
            "platform.claude.com",
            "https://api.anthropic.com/v1/messages",
            "claude-haiku-4-5",
            lambda prompt, model: {
                "model": model,
                "max_tokens": 1024,
                "tools": [{"type": "web_search_20250305", "name": "web_search", "max_uses": 3}],
                "messages": [{"role": "user", "content": prompt}],
            },
            read_anthropic,
            auth="anthropic",
        ),
        Provider(
            "perplexity",
            "Perplexity",
            "PERPLEXITY_API_KEY",
            "perplexity.ai/account/api",
            "https://api.perplexity.ai/v1/agent",
            "",
            lambda prompt, model: {
                "effort": "fast",
                "input": prompt,
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {"name": "song_facts", "schema": SCHEMA},
                },
            },
            read_responses,
        ),
        Provider(
            "parallel",
            "Parallel",
            "PARALLEL_API_KEY",
            "platform.parallel.ai",
            "https://api.parallel.ai/v1/responses",
            "parallel",
            lambda prompt, model: {
                "model": model,
                "input": prompt,
                "reasoning": {"effort": "low"},
                "text": openai_style_format(),
            },
            read_responses,
        ),
    )
}
DEFAULT_PROVIDER = "exa"


def provider_named(provider_id: str | None) -> Provider:
    return PROVIDERS.get(provider_id or "", PROVIDERS[DEFAULT_PROVIDER])


def request_facts(
    provider: Provider, track: Track, key: str, timeout: float = TIMEOUT
) -> list[Fact]:
    """Blocking; run off the UI loop."""
    # Only OpenAI and Anthropic take a model name; the others select by effort or product.
    override = os.environ.get(MODEL_ENVIRONMENT, "").strip()
    model = override if override and provider.id in {"openai", "anthropic"} else provider.model
    request = urllib.request.Request(
        provider.endpoint,
        data=json.dumps(provider.body(question(track), model)).encode(),
        headers=provider.headers(key),
        method="POST",
    )
    name = provider.name
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as error:
        if error.code in {401, 403}:
            raise FactsError(f"{name} rejected the API key. Press i to replace it.") from None
        if error.code in {402, 429}:
            raise FactsError(f"{name} rate limit or credits reached; facts paused.") from None
        raise FactsError(f"{name} returned HTTP {error.code}; no fact for this song.") from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise FactsError(f"Could not reach {name}; no fact for this song.") from None
    except ValueError:
        raise FactsError(f"{name} sent an unreadable response.") from None
    if not isinstance(payload, dict):
        return []
    return verified_facts(*provider.read(payload))


class Credentials:
    """Per provider: environment first, then a session-only key, then the OS credential store."""

    def __init__(self) -> None:
        self.session: dict[str, str] = {}

    def key(self, provider: Provider) -> str:
        if value := os.environ.get(provider.environment, "").strip():
            return value
        if provider.id in self.session:
            return self.session[provider.id]
        try:
            return keyring.get_password(KEYRING_SERVICE, provider.id) or ""
        except KeyringError:
            return ""

    def source(self, provider: Provider) -> str:
        if os.environ.get(provider.environment, "").strip():
            return "environment"
        if provider.id in self.session:
            return "session"
        return "keychain" if self.key(provider) else ""

    def save(self, provider: Provider, value: str, remember: bool) -> bool:
        """False when the credential store is unavailable; the key then lasts this session."""
        self.session.pop(provider.id, None)
        if remember:
            try:
                keyring.set_password(KEYRING_SERVICE, provider.id, value)
                return True
            except KeyringError:
                pass
        self.session[provider.id] = value
        return not remember

    def forget(self, provider: Provider) -> None:
        self.session.pop(provider.id, None)
        with contextlib.suppress(KeyringError):
            keyring.delete_password(KEYRING_SERVICE, provider.id)


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
