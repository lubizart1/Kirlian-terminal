# SPDX-License-Identifier: GPL-3.0-or-later
"""Optional sourced song notes. Only title, artist, album, and year leave the machine.

Each provider is asked the same question and returns notes with a source URL plus
the pages its search actually retrieved. A note is kept only when its URL matches
one of those retrieved pages, whichever provider answered. Notes are either a
"story" a source states directly, or a "reading": an interpretation the model
draws from what retrieved sources say, labeled as such on the card.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from urllib.parse import urlsplit

import keyring
from keyring.errors import KeyringError

from .library import Library, Track, display_text

KEYRING_SERVICE = "kirlian-terminal"
# Bump when the question changes so earlier answers are asked again.
PROMPT_VERSION = "2"
TIMEOUT = 90
HEADLINE_LIMIT = 70
BODY_LIMIT = 340
KINDS = ("story", "reading")

FACT = {
    "type": "object",
    "properties": {
        "kind": {"type": "string", "enum": list(KINDS)},
        "headline": {"type": "string"},
        "body": {"type": "string"},
        "source_url": {"type": "string"},
    },
    "required": ["kind", "headline", "body", "source_url"],
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
    """A readable reason the provider gave no facts. `detail` is the provider's own reply."""

    def __init__(self, message: str, detail: str = "") -> None:
        super().__init__(message)
        self.detail = detail


@dataclass(frozen=True)
class Fact:
    headline: str
    body: str
    source_title: str
    source_url: str
    published: str = ""
    kind: str = "story"
    provider: str = ""

    @property
    def source_label(self) -> str:
        """Page title, site, and year, e.g. "Air · uncut.co.uk, 2004"."""
        title = self.source_title.strip(" -–—|·:")
        host = urlsplit(self.source_url).netloc.casefold().removeprefix("www.")
        named = host in title.casefold() or title.casefold().replace(" ", "") in host
        label = title if not host or named else f"{title} · {host}"
        year = re.search(r"\b(1[89]|20)\d{2}\b", self.published)
        return f"{label}, {year[0]}" if year else label


def page_date(published: object) -> str:
    """Keep a stated date; drop relative ages such as Anthropic's "490 days ago".

    Those count from the page's last update, not its publication, so turning them
    into a year would misdate older articles.
    """
    text = str(published or "")
    return "" if re.search(r"\bago\b", text, re.IGNORECASE) else text


def fact_key(track: Track) -> str:
    return "\x1f".join(value.casefold() for value in (track.artist, track.album, track.title))


def question(track: Track) -> str:
    year = f", {track.year}" if track.year else ""
    return (
        f'Write up to three annotations for a listener about the song "{track.title}" by '
        f'{track.artist}, from the album "{track.album}"{year}, in the spirit of the best '
        "Genius annotations and liner notes. Search the web: interviews, reviews, "
        "encyclopedias, lyric annotation sites, books.\n\n"
        "Look for what makes this song itself interesting: what it is about, what its "
        "lyrics or title refer to, the circumstances or mood it was written in, where it "
        "sits in the artist's life and work, what it borrows or answers, and sounds a "
        "listener can hear and why they are there. Prefer the surprising and specific. "
        "Skip lists of credits, studios, engineers, release dates, chart positions, and "
        "generic praise unless there is a story in them. Do not describe the album in "
        "general, and nothing about a different song.\n\n"
        'Each annotation has a kind. "story": something a source states directly. '
        '"reading": an interpretation you draw by connecting what sources say, for '
        "example linking a lyric to an event an interview describes. Phrase a reading as "
        "a reading, not as fact. Every annotation, including readings, needs the exact "
        "URL of a page you retrieved that supports it. Headline under 9 words; body under "
        "55 words, plain and vivid. Return fewer, or none, rather than guessing.\n\n"
        'Reply with only JSON: {"facts": [{"kind": "story", "headline": "...", '
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
        kind = str(item.get("kind") or "story").casefold()
        facts.append(
            Fact(
                headline,
                body,
                title,
                source_url,
                source.get("published", ""),
                kind if kind in KINDS else "story",
            )
        )
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
                source(r.get("url"), r.get("title"), page_date(r.get("page_age")))
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
    model: str  # Sent as the model field when the API needs one.
    body: Callable[[str, str], dict]
    read: Callable[[dict], tuple[object, list[Source]]]
    auth: str = "bearer"  # bearer, x-api-key, or anthropic
    # (model, what to expect) suggestions; empty when the listener cannot choose.
    models: tuple[tuple[str, str], ...] = ()

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
            models=(
                ("gpt-5.4-mini", "Fast and inexpensive; solid everyday notes"),
                ("gpt-5.6-luna", "Cheapest; plainer notes"),
                ("gpt-6.1-sol", "Deeper reading of sources; costs more"),
            ),
        ),
        Provider(
            "anthropic",
            "Anthropic",
            "ANTHROPIC_API_KEY",
            "platform.claude.com",
            "https://api.anthropic.com/v1/messages",
            "claude-sonnet-5-5",
            lambda prompt, model: {
                "model": model,
                "max_tokens": 2048,
                "tools": [{"type": "web_search_20250305", "name": "web_search", "max_uses": 5}],
                "messages": [{"role": "user", "content": prompt}],
            },
            read_anthropic,
            auth="anthropic",
            models=(
                ("claude-sonnet-5-5", "Balanced: good stories and readings at moderate cost"),
                ("claude-haiku-5-5", "Fastest and cheapest; plainer notes"),
                ("claude-opus-5-5", "Most thorough; slowest and most expensive"),
            ),
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


@dataclass
class FactsConfig:
    """Providers in use, primary first (later ones are fallbacks), and chosen models."""

    order: list[str] = field(default_factory=list)
    models: dict[str, str] = field(default_factory=dict)

    @classmethod
    def load(cls, library: Library) -> FactsConfig:
        try:
            stored = json.loads(library.setting("facts_config") or "{}")
        except ValueError:
            stored = {}
        stored = stored if isinstance(stored, dict) else {}
        order = [p for p in stored.get("order") or [] if p in PROVIDERS]
        if not order and library.setting("facts_provider") in PROVIDERS:
            order = [library.setting("facts_provider")]  # Single-provider setup, 2026-10-26.
        models = stored.get("models") if isinstance(stored.get("models"), dict) else {}
        models = {
            p: str(m) for p, m in models.items() if p in PROVIDERS and PROVIDERS[p].models and m
        }
        return cls(list(dict.fromkeys(order)), models)

    def save(self, library: Library) -> None:
        library.set_setting(
            "facts_config", json.dumps({"order": self.order, "models": self.models})
        )

    def model(self, provider: Provider) -> str:
        """The model to request; "" for providers that pick their own."""
        return self.models.get(provider.id, provider.model) if provider.models else ""

    @property
    def providers(self) -> list[Provider]:
        return [PROVIDERS[p] for p in self.order]


def fetch_payload(
    provider: Provider, track: Track, key: str, model: str = "", timeout: float = TIMEOUT
) -> dict:
    """Blocking provider call. Raises FactsError with a listener-readable message."""
    request = urllib.request.Request(
        provider.endpoint,
        data=json.dumps(provider.body(question(track), model or provider.model)).encode(),
        headers=provider.headers(key),
        method="POST",
    )
    name = provider.name
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as error:
        detail = ""
        with contextlib.suppress(OSError, ValueError):
            detail = clip(error.read(2000).decode("utf-8", "replace"), 400)
        if error.code in {401, 403}:
            message = f"{name} rejected the API key. Press i to replace it."
        elif error.code in {402, 429}:
            message = f"{name} rate limit or credits reached."
        else:
            message = f"{name} returned HTTP {error.code}."
        raise FactsError(message, detail) from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise FactsError(f"Could not reach {name}.") from None
    except ValueError:
        raise FactsError(f"{name} sent an unreadable response.") from None
    if not isinstance(payload, dict):
        raise FactsError(f"{name} sent an unreadable response.")
    return payload


def request_facts(
    provider: Provider, track: Track, key: str, model: str = "", timeout: float = TIMEOUT
) -> list[Fact]:
    """Blocking; run off the UI loop."""
    payload = fetch_payload(provider, track, key, model, timeout)
    return [replace(f, provider=provider.name) for f in verified_facts(*provider.read(payload))]


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
    """Notes per provider and song, so each is requested once, not once per launch.

    Keyed by provider so providers can be compared, and by prompt version so a new
    question asks again. Rows from earlier versions are removed on open.
    """

    def __init__(self, library: Library) -> None:
        self.library = library
        with library.connect() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS facts (key TEXT PRIMARY KEY, facts TEXT NOT NULL)"
            )
            db.execute("DELETE FROM facts WHERE key NOT LIKE ?", (f"v{PROMPT_VERSION}\x1f%",))

    @staticmethod
    def key(provider_id: str, song: str) -> str:
        return f"v{PROMPT_VERSION}\x1f{provider_id}\x1f{song}"

    def get(self, provider_id: str, song: str) -> list[Fact] | None:
        with self.library.connect() as db:
            row = db.execute(
                "SELECT facts FROM facts WHERE key = ?", (self.key(provider_id, song),)
            ).fetchone()
        if row is None:
            return None
        try:
            return [Fact(**item) for item in json.loads(row[0])]
        except (ValueError, TypeError):
            return None

    def put(self, provider_id: str, song: str, facts: list[Fact]) -> None:
        with self.library.connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO facts VALUES (?, ?)",
                (self.key(provider_id, song), json.dumps([vars(fact) for fact in facts])),
            )
