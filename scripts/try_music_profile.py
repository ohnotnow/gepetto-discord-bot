#!/usr/bin/env python3
"""Dev tool for testing the music-profile ingestion pipeline against a pasted
chunk of a Discord music channel (copy-paste straight from the Discord UI).

This drives the PRODUCTION pipeline in src/content/music.py — the oEmbed
fetch, the LLM title parse, and the one-call-per-artist Discogs genre lookup
are the bot's real code. Tweak that module and this script shows you the
effect against real channel data, stage by stage:

    1. parse    (Discord paste -> who posted which YouTube link, when)
    2. oEmbed   (music.fetch_oembed: video title + channel name, free, no key)
    3. LLM      (music.parse_titles: is it music? primary artist,
                 collaborators, track)
    4. Discogs  (music.artist_genres: one release-search per unique artist)
    5. profiles (per-poster tally of artists, genres, styles)

Steps 1-2 are free and need no keys. --llm makes one batched LLM call.
--discogs (implies --llm) needs DISCOGS_TOKEN and makes ONE API call per
unique artist.

The bot's explore_discogs_artist tool is deliberately NOT used at ingestion
(each release lazy-loads genres with its own API request — see ant note
gepettodiscordbot-7qsQV). Use --explore "Artist Name" to run that real
recommendation-time path for a single artist and compare its output.

Examples:
    uv run python scripts/try_music_profile.py music-entertainment.txt
    uv run python scripts/try_music_profile.py music-entertainment.txt --llm
    uv run python scripts/try_music_profile.py music-entertainment.txt --llm --discogs
    uv run python scripts/try_music_profile.py music-entertainment.txt --limit 5 --llm
    uv run python scripts/try_music_profile.py music-entertainment.txt --explore "Arab Strap"

Env loading:
    Reads `.env` from the project root if present (KEY=value lines, #
    comments and blanks ignored). Existing shell env wins. Needs
    OPENAI_API_KEY for --llm and DISCOGS_TOKEN for --discogs. --model sets
    MUSIC_PARSE_MODEL for this run (the same env key the bot reads).

Outputs:
    JSON dumps to ./samples/output/music_profile_<timestamp>/ as
    links.json (per-link pipeline results) and profiles.json (per-poster
    tallies). `samples/` is gitignored.
"""

import argparse
import asyncio
import json
import logging
import os
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_MODEL = "openai/gpt-5.6-luna"


def _load_dotenv_if_present() -> None:
    env_path = PROJECT_ROOT / ".env"
    if not env_path.is_file():
        return
    for raw in env_path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        os.environ.setdefault(key, value)


def _setup_logging(verbose: bool) -> None:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter(
        fmt="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    ))
    discord_logger = logging.getLogger("discord")
    discord_logger.setLevel(logging.DEBUG if verbose else logging.WARNING)
    discord_logger.addHandler(handler)
    discord_logger.propagate = False
    logging.getLogger("LiteLLM").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)


def _get_chatbot():
    """Mirror main.get_chatbot() without dragging in the rest of main.py."""
    from src.providers import gpt
    return gpt.GPTModel()


def _heading(text: str) -> None:
    print(f"\n{'=' * 8} {text} {'=' * 8}")


# ---------------------------------------------------------------- stage 1

def parse_discord_paste(path: Path) -> list[dict]:
    """Pull (poster, timestamp, url) out of a Discord UI copy-paste.

    The paste format puts each author block on three lines:
        username
         —
        7/12/26, 7:03 PM
    and every message line after that belongs to them until the next block.
    """
    from src.content.music import YOUTUBE_URL_RE

    lines = path.read_text().splitlines()
    links = []
    seen_urls = set()
    poster = "unknown"
    posted_at = ""

    for i, line in enumerate(lines):
        if line.strip() == "—" and i > 0:
            poster = lines[i - 1].strip()
            posted_at = lines[i + 1].strip() if i + 1 < len(lines) else ""
            continue
        for url in YOUTUBE_URL_RE.findall(line):
            if url in seen_urls:
                continue
            seen_urls.add(url)
            links.append({"poster": poster, "posted_at": posted_at, "url": url})

    return links


# ---------------------------------------------------------------- stage 5

def build_profiles(links: list[dict], lookups: dict[str, dict]) -> dict:
    """Per-poster tally of artists, genres and styles."""
    profiles: dict = {}
    for link in links:
        profile = profiles.setdefault(link["poster"], {
            "links": 0, "music_links": 0,
            "artists": Counter(), "genres": Counter(), "styles": Counter(),
        })
        profile["links"] += 1
        if not link.get("is_music") or not link.get("artist"):
            continue
        profile["music_links"] += 1
        profile["artists"][link["artist"]] += 1
        lookup = lookups.get(link["artist"], {})
        if lookup.get("found"):
            for g in lookup["genres"]:
                profile["genres"][g] += 1
            for s in lookup["styles"]:
                profile["styles"][s] += 1
    return profiles


# ---------------------------------------------------------------- main

async def run(args: argparse.Namespace) -> None:
    from src.content import music

    chat_file = Path(args.chatfile)
    if not chat_file.is_file():
        sys.exit(f"No such file: {chat_file}")

    _heading("1. parsed links (poster attribution)")
    links = parse_discord_paste(chat_file)
    if args.limit:
        links = links[:args.limit]
    for link in links:
        print(f"  [{link['poster']}] {link['url']}  ({link['posted_at']})")
    print(f"\n  {len(links)} unique YouTube links")

    _heading("2. oEmbed metadata (free) — music.fetch_oembed")
    kept = []
    for link in links:
        meta = await music.fetch_oembed(link["url"])
        if meta is None:
            print(f"  [dead/blocked] {link['url']}")
            continue
        link.update(meta)
        kept.append(link)
        print(f"  [{link['poster']}] {meta['channel']} — {meta['title']}")
    links = kept

    if args.explore:
        _heading(f"explore_artist('{args.explore}') — the recommendation-time code path")
        from src.content import discogs
        print(await discogs.explore_artist(args.explore))

    if not args.llm:
        print("\nStopping before LLM parse (pass --llm to continue).")
        return

    _heading(f"3. LLM parse ({os.environ.get('MUSIC_PARSE_MODEL') or 'provider default'}) — music.parse_titles")
    try:
        await music.parse_titles(links, _get_chatbot())
    except music.MusicParseError as e:
        sys.exit(f"LLM parse failed (the bot would save nothing from this batch): {e}")
    for link in links:
        if link["is_music"]:
            collab = f" (with {', '.join(link['collaborators'])})" if link["collaborators"] else ""
            print(f"  MUSIC  [{link['poster']}] {link['artist']}{collab} — {link['track']}")
        else:
            print(f"  other  [{link['poster']}] {link['title'][:60]}")

    lookups: dict[str, dict] = {}
    if args.discogs:
        _heading("4. Discogs genres/styles (one search per artist) — music.artist_genres")
        artists = []
        for link in links:
            artist = link.get("artist")
            if link.get("is_music") and artist and artist not in artists:
                artists.append(artist)
        for artist in artists:
            lookups[artist] = await music.artist_genres(artist)
            status = "ok" if lookups[artist]["found"] else f"MISS ({lookups[artist].get('error')})"
            print(f"    {artist}: {status}")
            await asyncio.sleep(1.2)

        _heading("5. poster profiles")
        profiles = build_profiles(links, lookups)
        for poster, profile in profiles.items():
            print(f"\n  {poster}: {profile['links']} links, {profile['music_links']} music")
            if profile["artists"]:
                print(f"    artists: {', '.join(f'{a} ({c})' if c > 1 else a for a, c in profile['artists'].most_common())}")
            if profile["genres"]:
                print(f"    genres:  {', '.join(f'{g} ({c})' for g, c in profile['genres'].most_common(8))}")
            if profile["styles"]:
                print(f"    styles:  {', '.join(f'{s} ({c})' for s, c in profile['styles'].most_common(10))}")
    else:
        profiles = {}
        print("\nStopping before Discogs (pass --discogs for genres + profiles).")

    out_dir = PROJECT_ROOT / "samples" / "output" / f"music_profile_{datetime.now():%Y%m%d_%H%M%S}"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "links.json").write_text(json.dumps(links, indent=2))
    if profiles:
        serialisable = {
            poster: {
                "links": p["links"],
                "music_links": p["music_links"],
                "artists": dict(p["artists"]),
                "genres": dict(p["genres"]),
                "styles": dict(p["styles"]),
            }
            for poster, p in profiles.items()
        }
        (out_dir / "profiles.json").write_text(json.dumps(serialisable, indent=2))
    print(f"\nWrote {out_dir}/")


def main() -> None:
    parser = argparse.ArgumentParser(description="Test the music-profile ingestion pipeline (src/content/music.py) against a Discord paste.")
    parser.add_argument("chatfile", help="Text file of Discord channel copy-paste")
    parser.add_argument("--llm", action="store_true", help="Parse titles into artist/track with the LLM")
    parser.add_argument("--discogs", action="store_true", help="Look up genres/styles on Discogs (implies --llm)")
    parser.add_argument("--explore", metavar="ARTIST", help="Also run the real explore_artist path for one artist")
    parser.add_argument("--limit", type=int, help="Only process the first N links")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"LiteLLM model string; sets MUSIC_PARSE_MODEL for this run (default: {DEFAULT_MODEL})")
    parser.add_argument("--verbose", action="store_true", help="Show info-level logs")
    args = parser.parse_args()
    if args.discogs:
        args.llm = True

    _load_dotenv_if_present()
    os.environ["MUSIC_PARSE_MODEL"] = args.model  # same env key the bot reads
    _setup_logging(args.verbose)
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
