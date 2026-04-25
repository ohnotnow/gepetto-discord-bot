"""Direct-to-image prompt builders.

Companion to src/media/images.py. Where images.py writes prompts addressed
to an LLM (which then produces a structured tool-call with a distilled image
prompt), this module writes prompts addressed to a modern "smart" image
model (nano-banana, gpt-image, recraft, seedream, etc.) directly.

Signatures mirror images.py so callers can swap module references based
on the chosen model's strategy.

Theme-and-reasoning extraction for the dedup feedback loop happens after
generation via src/media/vlm.py — we no longer need the image model to
self-report what it drew.
"""

import os
from datetime import datetime

from . import images


def get_initial_chat_image_prompt(chat_history: str, previous_image_themes: str, user_bios: str = "") -> str:
    """Build a direct-to-image prompt from a day's chat history.

    The smart image model is instructed to pick one small unexpected detail
    from the chat and build a visually stunning composition around it,
    rather than trying to literally illustrate the conversation.
    """
    user_locations = os.getenv('USER_LOCATIONS', 'the UK towns of Bath and Manchester').strip()
    cat_descriptions = os.getenv('CAT_DESCRIPTIONS', '').strip()
    today_string = datetime.now().strftime("%Y-%m-%d")

    location_guidance = (
        f"If an outdoor setting fits, use {user_locations}. "
        "Avoid London unless it genuinely is the only thing that makes sense — the audience are not London fans."
    )

    cat_guidance = ""
    if cat_descriptions:
        cat_guidance = (
            f"If cats feature in the composition (only if the chat clearly invites them), "
            f"match these specific cats owned by people in the chat: {cat_descriptions}."
        )

    bio_guidance = ""
    if user_bios:
        bio_guidance = (
            "For atmospheric background colour, here are short bios of the people whose chat this is. "
            "Do NOT depict specific people or make the image about any one person — "
            "but let their nationalities, hobbies, or quirks subtly flavour the mood, setting, "
            f"or small details: {user_bios}"
        )

    extra_guidelines = images.get_extra_guidelines().strip()
    extras_block = ""
    if extra_guidelines:
        extras_block = f"Additional stylistic directions:\n{extra_guidelines}"

    return f"""Generate a single striking, beautiful image inspired by the chat conversation at the end of this prompt.

How to approach it:
- Read the chat below, but do NOT attempt to illustrate the whole conversation.
- Pick ONE small, unexpected detail — a texture, a mood, a food someone mentioned, a passing comment on the weather. The smaller and more specific, the better.
- If nothing stands out, use the overall emotional temperature of the day (frantic, lazy, celebratory, grumpy) as your starting point instead.
- Build a visually stunning composition around that single spark. Everything else from the chat: ignore it. Do not try to weave the rest in.

Style and mood:
- You have full creative freedom on medium, style, and setting.
- The result should make someone smile or pause with appreciation even if they don't know the original context. Think "photograph you'd hang on a wall" or "illustration that tells a small story at a glance" — not a surrealist puzzle that needs an artist's statement to decode.
- Ground the image in something recognisable and real, so the people who had the chat can look at it and think "ahh, clever, I see what you did there".
- If the chat contains someone genuinely struggling (relationship breakdown, pet or parent illness, real distress — not jokes), make the image cheerful and uplifting. Do NOT reflect their pain back at them.

Other context:
- Today's date is {today_string}.
- {location_guidance}
- {cat_guidance}
- {bio_guidance}
- {previous_image_themes}

{extras_block}

<chat_history>
{chat_history}
</chat_history>

Produce one image only."""


def get_creative_image_prompt(previous_image_themes: str, user_bios: str = "") -> str:
    """Direct prompt for quiet-chat days — total creative freedom from date/season."""
    now = datetime.now()
    date_string = now.strftime("%A, %d %B %Y")
    month = now.month

    user_locations = os.getenv('USER_LOCATIONS', 'the UK towns of Bath and Manchester').strip()
    location_guidance = (
        f"If an outdoor setting fits, use {user_locations}. "
        "Avoid London unless truly unavoidable."
    )

    if month in (12, 1, 2):
        season = "winter"
        season_hints = "short days, frost, bare branches, warm interiors, candlelight, woodsmoke, cold clear skies"
    elif month in (3, 4, 5):
        season = "spring"
        season_hints = "new growth, blossom, longer evenings, rain showers, birdsong, muddy paths, pale green"
    elif month in (6, 7, 8):
        season = "summer"
        season_hints = "long golden light, warm stone, open windows, thunderstorms, insects, overgrown gardens"
    else:
        season = "autumn"
        season_hints = "turning leaves, mist, harvest, conkers, damp earth, low sun, woodsmoke, gathering dark"

    bio_guidance = ""
    if user_bios:
        bio_guidance = (
            "For subtle atmospheric flavour (not portraiture), here are short bios of the people in the chat. "
            "Do NOT depict them or make the image about anyone specific — but let their hobbies or quirks "
            f"nudge the mood or small details: {user_bios}"
        )

    extra_guidelines = images.get_extra_guidelines().strip()
    extras_block = ""
    if extra_guidelines:
        extras_block = f"Additional stylistic directions:\n{extra_guidelines}"

    return f"""Generate a single striking, beautiful image of your own choosing.

Total creative freedom today — there was barely any chat to draw from, so you're inventing something from scratch.

Starting point (subtle, not heavy-handed):
- The date is {date_string}, and it's {season} in the UK ({season_hints}).
- Let the date or season nudge you somewhere unexpected — an obscure historical event, a half-remembered painting, a strange scientific fact, an imagined place, a feeling, a colour. One small spark, then run with it.

Style:
- Pick a bold artistic style and commit to it fully — a specific painter, film movement, photographic technique, printmaking method, textile pattern, pixel art, architectural rendering, botanical illustration. Anything that excites you. Don't hedge.
- The image should be visually striking and make someone pause with appreciation even with zero context. Think gallery wall, album cover, or a single frame from a film you'd rewind to look at again.

Other context:
- {location_guidance}
- {bio_guidance}
- {previous_image_themes}

{extras_block}

Produce one image only."""
