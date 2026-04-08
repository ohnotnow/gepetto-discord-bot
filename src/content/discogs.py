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

    logger.info(f"Discogs search: query='{query}', limit={limit}")

    try:
        results = client.search(query, type="artist")
    except Exception as e:
        logger.warning(f"Discogs search failed: {e}")
        return f"Discogs search failed: {e}"

    if not results or results.count == 0:
        logger.info(f"Discogs search: no results for '{query}'")
        return f"No artists found on Discogs matching '{query}'."

    lines = []
    for i, artist in enumerate(results):
        if i >= limit:
            break
        artist_id = artist.id
        name = artist.name if hasattr(artist, "name") else str(artist)
        lines.append(f"- {name} (ID: {artist_id})")

    output = f"Discogs artist search results for '{query}':\n" + "\n".join(lines)
    logger.info(f"Discogs search: returning {len(lines)} results for '{query}'")
    logger.debug(f"Discogs search response:\n{output}")
    return output


def _explore_artist_sync(artist_query: str) -> str:
    """
    Explore an artist's network on Discogs: members, side-projects, genres, key releases.
    Accepts an artist name (searched) or numeric ID.
    """
    client = _get_client()
    if not client:
        return "Discogs is not configured (missing DISCOGS_TOKEN)."

    logger.info(f"Discogs explore: artist_query='{artist_query}'")

    # Resolve artist - by ID if numeric, otherwise search
    artist = None
    if artist_query.strip().isdigit():
        logger.info(f"Discogs explore: looking up by ID {artist_query}")
        try:
            artist = client.artist(int(artist_query.strip()))
            _ = artist.name  # force fetch
        except Exception as e:
            logger.warning(f"Discogs artist lookup by ID failed: {e}")
            return f"Could not find artist with ID {artist_query}."
    else:
        logger.info(f"Discogs explore: searching for '{artist_query}'")
        try:
            results = client.search(artist_query, type="artist")
            if results and results.count > 0:
                artist = results[0]
                # Fetch the full artist object
                artist = client.artist(artist.id)
                logger.info(f"Discogs explore: resolved '{artist_query}' to '{artist.name}' (ID: {artist.id})")
        except Exception as e:
            logger.warning(f"Discogs artist search failed: {e}")
            return f"Discogs search failed: {e}"

    if not artist:
        logger.info(f"Discogs explore: no artist found for '{artist_query}'")
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
            for i, m in enumerate(members):
                if i >= 15:
                    break
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
            for i, g in enumerate(groups):
                if i >= 10:
                    break
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

    output = "\n\n".join(sections)
    logger.info(f"Discogs explore: returning data for '{artist.name}' — {len(sections)} sections (genres={genres}, styles={styles})")
    logger.debug(f"Discogs explore response:\n{output}")
    return output


async def search_artist(query: str) -> str:
    """Async wrapper for artist search."""
    return await asyncio.to_thread(_search_artist_sync, query)


async def explore_artist(artist_query: str) -> str:
    """Async wrapper for artist exploration."""
    return await asyncio.to_thread(_explore_artist_sync, artist_query)
