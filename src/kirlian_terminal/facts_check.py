# SPDX-License-Identifier: GPL-3.0-or-later
"""`kirlian --check-facts`: one live song-facts request per provider, explained.

Runs outside the player so a key and a provider's real response can be checked
directly. The key is never printed or written; the optional report holds the
provider's response, the retrieved pages, and which facts passed the source check.
"""

from __future__ import annotations

import getpass
import json
import sys
import time
from pathlib import Path

from .facts import (
    PROVIDERS,
    Credentials,
    FactsError,
    Provider,
    fetch_payload,
    json_object,
    model_for,
    verified_facts,
)
from .library import Track

SAMPLE = ("John Cale", "Paris 1919", "Paris 1919", "1973")


def sample_track(artist: str, title: str, album: str, year: str) -> Track:
    return Track(
        path="",
        title=title,
        artist=artist,
        album=album,
        album_artist=artist,
        album_id="",
        disc=1,
        track=1,
        duration=0,
        year=year,
        format="",
    )


def check_provider(provider: Provider, key: str, track: Track, out) -> tuple[bool, dict]:
    """Returns (responded, report entry)."""
    entry: dict = {"provider": provider.id, "model": model_for(provider)}
    started = time.monotonic()
    try:
        payload = fetch_payload(provider, track, key)
    except FactsError as error:
        entry |= {"error": str(error), "detail": error.detail}
        print(f"  Failed after {time.monotonic() - started:.1f} s: {error}", file=out)
        if error.detail:
            print(f"  {provider.name} said: {error.detail}", file=out)
        return False, entry
    elapsed = time.monotonic() - started
    answer, sources = provider.read(payload)
    proposed = (json_object(answer) or {}).get("facts")
    proposed = proposed if isinstance(proposed, list) else []
    kept = verified_facts(answer, sources)
    pages = {s["url"] for s in sources if s.get("url")}
    entry |= {
        "seconds": round(elapsed, 2),
        "retrieved_pages": sorted(pages),
        "proposed": proposed,
        "shown": [vars(fact) for fact in kept],
        "response": payload,
    }
    print(f"  Answered in {elapsed:.1f} s · {len(pages)} pages retrieved", file=out)
    if answer and json_object(answer) is None:
        print("  The answer was not the requested JSON.", file=out)
    print(
        f"  Facts proposed: {len(proposed)} · shown after the source check: {len(kept)}", file=out
    )
    for item in proposed:
        if not isinstance(item, dict):
            continue
        [fact] = verified_facts({"facts": [item]}, sources) or [None]
        headline = str(item.get("headline") or "(no headline)")[:60]
        if fact:
            print(f"    ✓ {fact.headline}", file=out)
            print(f"        {fact.body}", file=out)
            print(f"        Source: {fact.source_label} · {fact.source_url}", file=out)
        else:
            url = str(item.get("source_url") or "(none)")[:100]
            print(f"    ✗ {headline} — source {url} was not a retrieved page", file=out)
    if not kept:
        print("  No fact would be shown for this song.", file=out)
    return True, entry


def run_facts_check(
    choice: str | None,
    configured: str | None,
    song: tuple[str, str, str, str],
    report: Path | None,
    out=sys.stdout,
) -> int:
    credentials = Credentials()
    if choice == "all":
        providers = [p for p in PROVIDERS.values() if credentials.key(p)]
        if not providers:
            print(
                "No song-facts key found in the keychain or environment.\n"
                "Press i in the player to add one, or run --check-facts PROVIDER to paste one.",
                file=out,
            )
            return 1
    else:
        provider_id = choice or configured or "exa"
        if provider_id not in PROVIDERS:
            print(
                f"Unknown provider {provider_id!r}. Choose: {', '.join(PROVIDERS)}, all.", file=out
            )
            return 2
        providers = [PROVIDERS[provider_id]]
    track = sample_track(*song)
    year = f", {track.year}" if track.year else ""
    print(f'Song: {track.artist} — "{track.title}" ({track.album}{year})', file=out)
    print("Sent: title, artist, album, and year only. The key is never printed.\n", file=out)
    entries = []
    failures = 0
    for provider in providers:
        source = credentials.source(provider)
        key = credentials.key(provider)
        if not key and sys.stdin.isatty():
            key = getpass.getpass(f"{provider.name} API key (not saved): ").strip()
            source = "typed for this check"
        model = f" ({model_for(provider)})" if model_for(provider) else ""
        print(f"{provider.name}{model} · key from {source or 'nowhere'}", file=out)
        if not key:
            print(f"  No key. Set {provider.environment} or press i in the player.\n", file=out)
            failures += 1
            continue
        responded, entry = check_provider(provider, key, track, out)
        failures += not responded
        entries.append(entry)
        print(file=out)
    if report:
        report.write_text(json.dumps({"song": song, "results": entries}, indent=2) + "\n")
        print(f"Report saved to {report}. It contains no API key.", file=out)
    return 1 if failures else 0
