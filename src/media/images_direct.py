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

    return f"""Generate one striking, beautiful image inspired by the chat conversation at the end of this prompt.

THE MOVE — read the chat, then pick ONE small, specific detail: a texture, a mood, a food someone mentioned, a passing weather remark, a turn of phrase. Now do NOT illustrate that detail. Transpose it into a strong, committed visual register from somewhere else entirely. Examples of the kind of leap to make:
- Edo-period woodblock print
- mid-century scientific or botanical plate
- vintage Penguin Classics cover
- Soviet propaganda print
- Studio Ghibli background still
- 1950s Technicolor B-movie poster
- Bauhaus / Constructivist diagram
- Ladybird Book illustration
- 1960s Blue Note jazz album cover (Reid Miles / Francis Wolff)
- William Morris-style textile pattern
- Saul Bass title-sequence still
- Magritte- or New Yorker-cover-style visual pun where the *composition itself* is the wit (no caption needed)

These are examples, not a menu — surprise yourself. The further the chosen register sits from the original chat detail, the better the image tends to be. If nothing in the chat stands out at all, use the overall emotional temperature of the day (frantic, lazy, celebratory, grumpy) as the spark instead.

COMMIT TO THE STYLE. Whatever register you pick, render it with the *full* visual vocabulary of that genre — typography, palette, paper stock, brushwork, mannerisms, period quirks. Hedging produces beige. The audience are technically-minded people who appreciate cleverness expressed through *design*, not through punchlines.

DO NOT:
- Render the chat detail literally. A photo-realistic street with a bin in it, a cup of coffee because someone mentioned a coffee, a still life of an object someone named — none of these will delight or amaze.
- Render text from the chat as the subject. No sticky notes, Post-its, handwritten signs, chalkboards, or labels with the quote written on them. Text is allowed only when the chosen genre actively requires it (film poster, comic panel, propaganda print, book cover) — and then it must be in-genre, not a transcribed quote from the chat.
- Default to product photography. A single ceramic object on a neutral background is the visual equivalent of a shrug.
- Lean on a verbal joke or pun rendered as text. Wit through composition, not captions.
- Try to weave the whole conversation in. One spark, then transposition. Everything else: ignore it.

THE BAR — the people who had the chat should look at the image and think "ah, clever, and what a great-looking thing." Someone with no context should still pause and want to look longer. Gallery wall, not Slack reaction.

ONE EXCEPTION — if the chat contains someone in genuine distress (relationship breakdown, pet or parent illness, real hardship — not jokes), make the image warm, cheerful and uplifting. Do not reflect their pain back at them.

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

    return f"""Generate one striking, beautiful image of your own choosing.

There was barely any chat to draw from today, so you're inventing from scratch.

THE SPARK — the date is {date_string}, and it's {season} in the UK ({season_hints}). Let the date or season nudge you somewhere unexpected: an obscure historical event, a half-remembered painting, a strange scientific fact, an imagined place, a feeling, a colour. One small spark, then run with it.

COMMIT TO A REGISTER. Pick a strong visual style and render it with its full vocabulary — typography, palette, brushwork, period quirks. Examples of the kind of register to commit to:
- Edo-period woodblock print
- mid-century scientific or botanical plate
- vintage Penguin Classics cover
- Soviet propaganda print
- Studio Ghibli background still
- 1950s Technicolor B-movie poster
- Bauhaus / Constructivist diagram
- Ladybird Book illustration
- 1960s Blue Note jazz album cover (Reid Miles / Francis Wolff)
- William Morris-style textile pattern
- Saul Bass title-sequence still
- Magritte- or New Yorker-cover-style visual pun where the *composition itself* is the wit (no caption needed)

Examples, not a menu — surprise yourself. Hedging produces beige. The audience are technically-minded people who appreciate cleverness expressed through design, not through punchlines.

DO NOT:
- Default to product photography. A single object on a neutral background is the visual equivalent of a shrug.
- Render text as the subject — no sticky notes, signs, labels. Text is allowed only when the chosen genre actively requires it (poster, book cover, comic panel) and then must be in-genre.
- Be too on-the-nose with the season. A pumpkin in October, a daffodil in spring — that's lazy. Use the season as flavour, not subject.
- Lean on a verbal joke rendered as text. Wit through composition, not captions.

THE BAR — the image should be visually striking even with zero context. Gallery wall, album cover, or a single frame from a film you'd rewind to look at again.

Other context:
- {location_guidance}
- {bio_guidance}
- {previous_image_themes}

{extras_block}

Produce one image only."""
