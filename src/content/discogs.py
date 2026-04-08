"""
Discogs API integration for music recommendations.

Wraps python3-discogs-client to provide artist search and network exploration,
used as LLM tools so the bot can make grounded music recommendations.
"""

import asyncio
import logging
import os
from functools import lru_cache

import discogs_client

logger = logging.getLogger(__name__)

USER_AGENT = "GepettoDiscordBot/1.0"


def _get_client() -> discogs_client.Client | None:
    token = os.getenv("DISCOGS_TOKEN")
    if not token:
        return None
    return discogs_client.Client(USER_AGENT, user_token=token)


def _search_artist_sync(query: str, limit: int = 5) -> str:
    """Search Discogs for artists matching a query. Returns formatted text."""
    client = _get_client()
    if not client:
        return "Discogs is not configured (missing DISCOGS_TOKEN)."

    try:
        results = client.search(query, type="artist")
    except Exception as e:
        logger.warning(f"Discogs search failed: {e}")
        return f"Discogs search failed: {e}"

    if not results or results.count == 0:
        return f"No artists found on Discogs matching '{query}'."

    lines = []
    for artist in results[:limit]:
        artist_id = artist.id
        name = artist.name if hasattr(artist, "name") else str(artist)
        lines.append(f"- {name} (ID: {artist_id})")

    return f"Discogs artist search results for '{query}':\n" + "\n".join(lines)


def _explore_artist_sync(artist_query: str) -> str:
    """
    Explore an artist's network on Discogs: members, side-projects, genres, key releases.
    Accepts an artist name (searched) or numeric ID.
    """
    client = _get_client()
    if not client:
        return "Discogs is not configured (missing DISCOGS_TOKEN)."

    # Resolve artist - by ID if numeric, otherwise search
    artist = None
    if artist_query.strip().isdigit():
        try:
            artist = client.artist(int(artist_query.strip()))
            _ = artist.name  # force fetch
        except Exception as e:
            logger.warning(f"Discogs artist lookup by ID failed: {e}")
            return f"Could not find artist with ID {artist_query}."
    else:
        try:
            results = client.search(artist_query, type="artist")
            if results and results.count > 0:
                artist = results[0]
                # Fetch the full artist object
                artist = client.artist(artist.id)
        except Exception as e:
            logger.warning(f"Discogs artist search failed: {e}")
            return f"Discogs search failed: {e}"

    if not artist:
        return f"No artist found on Discogs matching '{artist_query}'."

    sections = [f"## {artist.name}"]

    # Profile / bio
    if hasattr(artist, "profile") and artist.profile:
        profile = artist.profile[:500]
        if len(artist.profile) > 500:
            profile += "..."
        sections.append(f"**Bio:** {profile}")

    # Members (for bands) - reveals side-project potential
    try:
        members = artist.members
        if members:
            member_names = []
            for m in members[:15]:
                name = m.name if hasattr(m, "name") else str(m)
                member_names.append(f"{name} (ID: {m.id})")
            sections.append("**Members:** " + ", ".join(member_names))
    except Exception:
        pass

    # Groups this artist is in (for solo artists)
    try:
        groups = artist.groups
        if groups:
            group_names = []
            for g in groups[:10]:
                name = g.name if hasattr(g, "name") else str(g)
                group_names.append(f"{name} (ID: {g.id})")
            sections.append("**Also in:** " + ", ".join(group_names))
    except Exception:
        pass

    # Key releases - get genres and styles from their discography
    genres = set()
    styles = set()
    notable_releases = []
    try:
        releases = artist.releases
        for i, release in enumerate(releases):
            if i >= 30:  # don't paginate forever
                break
            try:
                # Collect genres and styles
                if hasattr(release, "genres"):
                    genres.update(release.genres or [])
                if hasattr(release, "styles"):
                    styles.update(release.styles or [])

                # Track notable releases (main releases, not appearances)
                if len(notable_releases) < 10:
                    title = release.title if hasattr(release, "title") else str(release)
                    year = getattr(release, "year", "")
                    year_str = f" ({year})" if year else ""
                    # Get other artists on this release for collaboration info
                    notable_releases.append(f"{title}{year_str}")
            except Exception:
                continue
    except Exception as e:
        logger.debug(f"Could not fetch releases for {artist.name}: {e}")

    if genres:
        sections.append("**Genres:** " + ", ".join(sorted(genres)))
    if styles:
        sections.append("**Styles:** " + ", ".join(sorted(styles)))
    if notable_releases:
        sections.append("**Key releases:** " + " | ".join(notable_releases))

    return "\n\n".join(sections)


async def search_artist(query: str) -> str:
    """Async wrapper for artist search."""
    return await asyncio.to_thread(_search_artist_sync, query)


async def explore_artist(artist_query: str) -> str:
    """Async wrapper for artist exploration."""
    return await asyncio.to_thread(_explore_artist_sync, artist_query)
