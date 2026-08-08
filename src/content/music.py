"""
Music link enrichment pipeline: oEmbed -> LLM parse -> Discogs genres.

Ported from the validated spike scripts/try_music_profile.py. Pure content
pipeline — no Discord/platform imports — shared by the daily extraction task
and the backfill command.

Costs per batch of links: one free oEmbed request per link, ONE batched LLM
call, and ONE Discogs release-search per unique artist. Do not use
explore_artist() here: it lazy-loads ~30 releases per artist, each a separate
API request (see ant note gepettodiscordbot-7qsQV).
"""

import asyncio
import json
import logging
import os
import re

import requests

from src.content.discogs import USER_AGENT, _get_client

logger = logging.getLogger('discord')

YOUTUBE_URL_RE = re.compile(
    r'https?://(?:www\.)?(?:youtube\.com/watch\?v=[\w-]+|youtu\.be/[\w-]+)'
)

PARSE_SYSTEM_PROMPT = """You are given a numbered list of YouTube videos (channel name and video title) posted in a Discord music channel. For each one, decide whether it is a piece of music - a song, track, album, live session, or music video. Film trailers, TV/film clips, video essays and other non-music videos are not music.

For music entries, extract:
- "artist": the ONE primary artist, named the way a music database would catalogue them. Strip featured guests and collaboration phrasing: "Tricky feat. Polly Jean Harvey" -> "Tricky"; "Alan Sparhawk with Trampled by Turtles" -> "Alan Sparhawk"; "Pendulum, Bullet For My Valentine" -> "Pendulum". If you genuinely cannot tell, use null.
- "collaborators": any other named artists on the track, as a list of strings (often empty).
- "track": the track title.

Clean up noise: drop suffixes like "(Official Video)", "[OFFICIAL VIDEO]", "(Official Audio)", "VEVO", "- Topic", surrounding quotes. If the title does not name the artist, the channel name may be the artist.

Respond ONLY with valid JSON in this exact format:
{"entries": [{"index": 1, "is_music": true, "artist": "primary artist or null", "collaborators": ["other artist"], "track": "track title or null"}]}

Return one entry per input line, using the same index numbers."""


class MusicParseError(Exception):
    """The LLM's parse response was unusable.

    Callers must not save any links from the affected batch: the daily task
    stores non-music links permanently (is_music=0) and dedupes on URL, so a
    swallowed parse failure would misclassify a whole day's links forever.
    """


def _fetch_oembed_sync(url: str) -> dict | None:
    """Fetch title + channel for a YouTube URL via the free oEmbed endpoint."""
    try:
        response = requests.get(
            "https://www.youtube.com/oembed",
            params={"url": url, "format": "json"},
            headers={"User-Agent": USER_AGENT},
            timeout=10,
        )
    except requests.RequestException as e:
        logger.info(f"oEmbed request failed for {url}: {e}")
        return None
    if response.status_code != 200:
        # 400 = dead/private video; skip the link, it's not an error
        logger.info(f"oEmbed returned {response.status_code} for {url}")
        return None
    data = response.json()
    return {"title": data.get("title", ""), "channel": data.get("author_name", "")}


async def fetch_oembed(url: str) -> dict | None:
    """Async wrapper for the oEmbed fetch."""
    return await asyncio.to_thread(_fetch_oembed_sync, url)


async def parse_titles(links: list[dict], chatbot) -> None:
    """One batched LLM call: title/channel -> is_music, artist, collaborators, track.

    Mutates each link dict in place. Raises MusicParseError on an unusable
    response — never swallow it into "everything is non-music".

    Model comes from MUSIC_PARSE_MODEL (a full LiteLLM string, read at call
    time so tests can monkeypatch); empty means the provider default.
    """
    if not links:
        return

    numbered = []
    for n, link in enumerate(links, start=1):
        numbered.append(f'{n}. channel: "{link["channel"]}" title: "{link["title"]}"')

    model = os.getenv("MUSIC_PARSE_MODEL", "")
    response = await chatbot.chat(
        [
            {"role": "system", "content": PARSE_SYSTEM_PROMPT},
            {"role": "user", "content": "\n".join(numbered)},
        ],
        model=model,
        json_mode=True,
        tools=[],
    )

    response_text = response.message.strip()
    if response_text.startswith("```"):
        response_text = response_text.split("```")[1]
        if response_text.startswith("json"):
            response_text = response_text[4:]

    try:
        parsed = json.loads(response_text)
    except json.JSONDecodeError as e:
        logger.error(f"Music parse: LLM response was not valid JSON: {e}")
        raise MusicParseError(f"LLM response was not valid JSON: {e}") from e

    entries = parsed.get("entries") if isinstance(parsed, dict) else None
    if not isinstance(entries, list):
        logger.error("Music parse: LLM response JSON had no 'entries' list")
        raise MusicParseError("LLM response JSON had no 'entries' list")

    by_index = {e.get("index"): e for e in entries if isinstance(e, dict)}
    for n, link in enumerate(links, start=1):
        entry = by_index.get(n, {})
        link["is_music"] = bool(entry.get("is_music", False))
        link["artist"] = entry.get("artist") or None
        link["collaborators"] = entry.get("collaborators") or []
        link["track"] = entry.get("track") or None


def _artist_genres_sync(artist: str, sample_releases: int = 8) -> dict:
    """One Discogs release-search for an artist; genres/styles from the
    search payload itself.

    Only reads `.data` on the result objects — attribute access like
    release.genres on the lazy objects triggers one HTTP fetch per release.
    """
    client = _get_client()
    if not client:
        return {"found": False, "error": "DISCOGS_TOKEN not set", "genres": [], "styles": []}

    logger.info(f"Discogs genre lookup: artist='{artist}'")
    try:
        results = client.search(artist=artist, type="release")
    except Exception as e:
        logger.warning(f"Discogs genre lookup failed for '{artist}': {e}")
        return {"found": False, "error": str(e), "genres": [], "styles": []}

    genres: dict = {}
    styles: dict = {}
    sampled = 0
    try:
        for i, release in enumerate(results):
            if i >= sample_releases:
                break
            data = getattr(release, "data", None) or {}
            for g in data.get("genre") or []:
                genres[g] = genres.get(g, 0) + 1
            for s in data.get("style") or []:
                styles[s] = styles.get(s, 0) + 1
            sampled += 1
    except Exception as e:
        logger.warning(f"Discogs genre lookup failed for '{artist}': {e}")

    if sampled == 0:
        return {"found": False, "error": "no releases found", "genres": [], "styles": []}

    return {
        "found": True,
        "sampled_releases": sampled,
        "genres": sorted(genres, key=genres.get, reverse=True),
        "styles": sorted(styles, key=styles.get, reverse=True),
    }


async def artist_genres(artist: str) -> dict:
    """Async wrapper for the Discogs genre lookup."""
    return await asyncio.to_thread(_artist_genres_sync, artist)


async def enrich_links(links: list[dict], chatbot, throttle_seconds: float = 1.2) -> None:
    """Run the full pipeline over a batch of link dicts, in place.

    Input: dicts with at least a "url" key; caller-owned keys (poster,
    timestamps) are left untouched. Adds title/channel/is_music/artist/
    collaborators/track/genres/styles. Dead links (no oEmbed) are dropped
    from the list. Raises MusicParseError if the LLM parse fails — callers
    must not save anything from the batch.
    """
    kept = []
    for link in links:
        meta = await fetch_oembed(link["url"])
        if meta is None:
            logger.info(f"Dropping dead/unfetchable link {link['url']}")
            continue
        link.update(meta)
        kept.append(link)
    links[:] = kept

    if not links:
        return

    await parse_titles(links, chatbot)

    artists = []
    for link in links:
        artist = link.get("artist")
        if link.get("is_music") and artist and artist not in artists:
            artists.append(artist)

    lookups = {}
    for artist in artists:
        lookups[artist] = await artist_genres(artist)
        status = "ok" if lookups[artist]["found"] else f"miss ({lookups[artist].get('error')})"
        logger.info(f"Discogs genre lookup for '{artist}': {status}")
        await asyncio.sleep(throttle_seconds)

    for link in links:
        lookup = lookups.get(link.get("artist"), {})
        link["genres"] = lookup.get("genres", []) if lookup.get("found") else []
        link["styles"] = lookup.get("styles", []) if lookup.get("found") else []
