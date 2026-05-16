"""News-bulletin pipeline.

Fetches BBC RSS feeds, filters out obviously grim items via a small keyword
list, and uses an LLM to synthesise the survivors into a handful of themed
mini-bulletins in a 30-second-radio-slot voice.

Two production consumers:

- The daily image pipeline (ait gepetto-discord-bot-GZUcn) — bulletins feed
  the decoy slot of the corpse pipeline (see ant gepettodiscordbot-Ed6UZ
  for the design rationale).
- A bot tool call (ait gepetto-discord-bot-PQNMc) — users can ask the bot
  for the day's news directly.

The debugging/iteration script is at scripts/try_news_filter.py.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass

import feedparser

from src.utils.constants import DISCORD_MESSAGE_LIMIT, NEWS_CACHE_TTL_HOURS

logger = logging.getLogger("discord")


FEEDS = {
    "uk": "http://feeds.bbci.co.uk/news/uk/rss.xml",
    "politics": "http://feeds.bbci.co.uk/news/politics/rss.xml",
    "technology": "http://feeds.bbci.co.uk/news/technology/rss.xml",
    "entertainment_and_arts": "http://feeds.bbci.co.uk/news/entertainment_and_arts/rss.xml",
}

# Cheap deterministic pre-filter. Matched against title, summary, and BBC
# category tags. The picker-level SENSITIVE_TOPICS_GUARD downstream remains
# the load-bearing safety layer; this list is hygiene, not safety.
GRIM_KEYWORDS = [
    r"\bwars?\b",
    r"\bmurders?\b",
    r"\bshootings?\b",
    r"\bkillings?\b",
    r"\bvictims?\b",
    r"\beurovision\b",
]
GRIM_RE = re.compile("|".join(GRIM_KEYWORDS), re.IGNORECASE)

_HTML_TAG_RE = re.compile(r"<[^>]+>")


@dataclass
class Item:
    feed: str
    title: str
    summary: str
    categories: list[str]


@dataclass
class Bulletin:
    heading: str
    body: str
    sources: list[Item]


def clean_summary(raw: str) -> str:
    """Strip HTML and collapse whitespace. No truncation — the whole summary
    is the judgement-call data for both the keyword filter and the LLM."""
    text = _HTML_TAG_RE.sub("", raw or "")
    return " ".join(text.split())


def fetch_feed(name: str, url: str, *, per_feed: int) -> list[Item]:
    """Pull up to `per_feed` entries from a single RSS feed."""
    parsed = feedparser.parse(url)
    items: list[Item] = []
    for entry in parsed.entries[:per_feed]:
        categories = [t.get("term", "") for t in entry.get("tags", []) if t.get("term")]
        items.append(
            Item(
                feed=name,
                title=entry.get("title", "").strip(),
                summary=entry.get("summary", "").strip(),
                categories=categories,
            )
        )
    return items


def dedupe(items: list[Item]) -> list[Item]:
    """Drop items whose (case-folded) title has already been seen."""
    seen: set[str] = set()
    out: list[Item] = []
    for item in items:
        key = item.title.lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def grim_match(item: Item) -> str | None:
    """Return the matched keyword if any GRIM_KEYWORD hits the item's title,
    summary, or category tags. Returns None for clean items."""
    haystacks = [item.title, item.summary] + item.categories
    for haystack in haystacks:
        match = GRIM_RE.search(haystack)
        if match:
            return match.group(0)
    return None


LLM_SYSTEM_PROMPT_TEMPLATE = """\
You are the news editor for a Discord server full of Slashdot-era geeks:
IT/electrical engineering/robotics/data science backgrounds, politically
engaged in a process-curious way, irreverent, allergic to vapid news. They
DO NOT CARE ABOUT SPORT.

You'll be given today's BBC headlines plus standfirst summaries. Your job
is to produce a small handful of THEMED MINI-BULLETINS, in the voice of a
slightly droll radio newsreader. Each bulletin weaves the relevant stories
into 2-4 sentences of running prose. Use natural transitions —
"Meanwhile...", "In tech...", "Elsewhere...", "Closer to home..." — so it
reads like a bulletin, not a bulleted list. USE THE SUMMARIES, not just
the headlines: BBC headlines are subbed for clickability; the summary
carries the actual context.

STEP 1 — SKIP anything that is:
- SPORT of any kind (football, cricket, rugby, F1, etc.)
- bereavement, illness, death, suicide, miscarriage, child abuse, sexual
  abuse, victims of crime
- terrorism, war, mass violence, refugee/migration hardship as the central
  subject
- dull bureaucratic news (junior reshuffles, routine announcements,
  who-is-X explainers)
- pure celebrity wealth or sentiment fluff (X is now a billionaire, Y in
  tears at a charity feat)
- BBC navel-gazing about its own shows when the angle is just "show was
  good/bad"

STEP 2 — From the survivors, write AT MOST {max_bulletins} thematic
bulletins. Common shapes: UK politics, world/Europe, tech industry,
science/curiosities, culture. Skip any category that has nothing strong
to say in it today. Fewer, stronger bulletins beat more weaker ones —
if you can only honestly fill 2 categories, produce 2.

HARD LENGTH BUDGET — the whole set of bulletins must fit a 30-second
radio news slot. That is roughly 75-90 WORDS TOTAL across ALL bulletin
bodies combined. Not per bulletin — total. Resist quips, asides, and
clever flourishes; they cost words. Plain, fast, specific.

Each bulletin:
- has a short HEADING (3-6 words, plain category-ish, e.g. "UK politics",
  "In tech", "Science and curiosities")
- has a BODY of ONE sentence (two short ones at the absolute most),
  weaving 1-4 underlying stories together with a "meanwhile" or
  similar if it earns it. No editorialising — the facts carry it.
- lists the SOURCE NUMBERS of the items it draws from (the numbers from
  the input list)

Reply with ONLY a JSON object of this shape, no prose before or after:
{{"bulletins": [
  {{"heading": "<short heading>",
   "body": "<2-4 sentence prose digest>",
   "sources": [<int>, ...]}}
]}}
"""


def _format_items_for_prompt(items: list[Item]) -> str:
    blocks: list[str] = []
    for i, item in enumerate(items):
        block = f"{i + 1}. [{item.feed}] {item.title}"
        summary = clean_summary(item.summary)
        if summary:
            block += f"\n   summary: {summary}"
        blocks.append(block)
    return "\n".join(blocks)


async def synthesise_bulletins(
    items: list[Item],
    chatbot,
    *,
    max_bulletins: int = 5,
    model: str | None = None,
) -> list[Bulletin]:
    """Run one batched LLM call. Filters and synthesises the given items into
    at most `max_bulletins` themed mini-bulletins. Returns [] if the call or
    JSON parse fails.

    `chatbot` is any object with an async `chat(messages, json_mode=..., ...)`
    method matching BaseModel.chat — see src/providers/base.py.
    """
    if not items:
        return []
    numbered = _format_items_for_prompt(items)
    messages = [
        {
            "role": "system",
            "content": LLM_SYSTEM_PROMPT_TEMPLATE.format(max_bulletins=max_bulletins),
        },
        {"role": "user", "content": f"<items>\n{numbered}\n</items>"},
    ]
    chat_kwargs = {"json_mode": True, "temperature": 0.4}
    if model:
        chat_kwargs["model"] = model
    response = await chatbot.chat(messages, **chat_kwargs)
    raw = getattr(response, "message", "") or ""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("[news:synth] could not parse JSON: %r", raw[:200])
        return []

    bulletins: list[Bulletin] = []
    for entry in data.get("bulletins", []):
        heading = str(entry.get("heading", "")).strip()
        body = str(entry.get("body", "")).strip()
        sources: list[Item] = []
        for n in entry.get("sources", []):
            try:
                idx = int(n) - 1
            except (TypeError, ValueError):
                continue
            if 0 <= idx < len(items):
                sources.append(items[idx])
        if heading and body:
            bulletins.append(Bulletin(heading=heading, body=body, sources=sources))
    return bulletins


async def get_news_bulletins(
    chatbot,
    *,
    feeds: list[str] | None = None,
    per_feed: int = 10,
    max_bulletins: int = 5,
    model: str | None = None,
    news_store=None,
    max_age_hours: float = NEWS_CACHE_TTL_HOURS,
) -> list[Bulletin]:
    """Fetch → dedupe → keyword-cull → LLM-synthesise. End-to-end entry point.

    Args:
        chatbot: an object with an async chat() method (see BaseModel.chat).
        feeds: list of feed names from FEEDS to fetch. None = all four.
        per_feed: max entries to pull per RSS feed.
        max_bulletins: cap on bulletins the LLM may return.
        model: optional model override passed through to chatbot.chat().
        news_store: optional NewsStore. When passed, the cache is consulted
            first and a fresh fetch is only made on miss (or stale cache).
            When omitted, every call fetches fresh.
        max_age_hours: TTL passed to the store's freshness check. Ignored
            when news_store is None.

    Returns themed bulletins in a 30-second-radio-slot voice. See ant
    gepettodiscordbot-Ed6UZ for the design context and ait
    gepetto-discord-bot-YHETx for the cache.
    """
    if news_store is not None:
        cached = news_store.get_cached_bulletins(max_age_hours)
        if cached is not None:
            return cached

    feed_names = feeds if feeds is not None else list(FEEDS.keys())
    all_items: list[Item] = []
    for name in feed_names:
        url = FEEDS.get(name)
        if not url:
            logger.warning("[news:fetch] unknown feed name %r — skipping", name)
            continue
        all_items.extend(fetch_feed(name, url, per_feed=per_feed))

    deduped = dedupe(all_items)
    survivors = [item for item in deduped if grim_match(item) is None]
    logger.info(
        "[news:cull] fetched=%d deduped=%d survivors=%d culled=%d",
        len(all_items), len(deduped), len(survivors), len(deduped) - len(survivors),
    )
    bulletins = await synthesise_bulletins(
        survivors, chatbot, max_bulletins=max_bulletins, model=model
    )

    if news_store is not None and bulletins:
        # Only cache non-empty results — a transient fetch failure (zero
        # survivors, empty LLM reply) shouldn't poison the cache.
        news_store.save_bulletins(bulletins)

    return bulletins


def format_bulletins_for_discord(
    bulletins: list[Bulletin],
    *,
    limit: int = DISCORD_MESSAGE_LIMIT,
) -> str:
    """Format bulletins as a single Discord-ready string: bold heading then
    body for each, separated by blank lines. If the total exceeds `limit`,
    drop bulletins from the end rather than truncating mid-bulletin."""
    if not bulletins:
        return ""

    blocks = [f"**{b.heading}**\n{b.body}" for b in bulletins]
    out = "\n\n".join(blocks)
    while blocks and len(out) > limit:
        blocks.pop()
        out = "\n\n".join(blocks)
    return out
