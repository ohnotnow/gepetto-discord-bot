"""
Exquisite Corpse image prompt pipeline.

Builds the daily chat-image prompt through a sequence of *blind* LLM calls.
Each slice (detail, decoy, mood, style) sees only a sliver of context, and
the final assembler sees no chat history at all — so it cannot reconstruct
literal chat events as a "flat-lay product photo".

Named after the surrealist parlour game / British "Consequences" — each
contributor draws one panel without seeing the others.

See `ant show gepettodiscordbot-AkRXV` for the wider image-generation flow
and `ait show gepetto-discord-bot-xhoCp` for the epic this sits under.
"""

from __future__ import annotations

import json
import logging
import os
import random
from datetime import datetime
from typing import Optional

logger = logging.getLogger("discord")

DECOY_PROBABILITY = 0.05

# Stylistic hand-brake: the LLM has clear favourites here and will return them
# every time unless told otherwise. These are stitched into the style anti-list
# alongside whatever has been picked recently.
EVERGREEN_STYLE_BANS = [
    "Dutch Golden Age",
    "Vermeer",
    "Hieronymus Bosch",
    "De Chirico",
    "Salvador Dalí",
    "surrealism in general",
    "Studio Ghibli",
    "Wes Anderson symmetry",
]

EVERGREEN_DECOY_BANS = [
    "a violin",
    "a teacup",
    "an octopus",
    "a lighthouse",
    "an old library",
    "a cathedral",
    "a typewriter",
    "a hot air balloon",
]


def _exclude_clause(label: str, items: list[str]) -> str:
    if not items:
        return ""
    rendered = "; ".join(items)
    return f"\n\n{label}: {rendered}"


def _clean_pick(raw: str) -> str:
    """Strip the usual LLM preamble noise from a one-shot pick."""
    if not raw:
        return ""
    text = raw.strip()
    # Drop wrapping quotes, common preambles, trailing punctuation.
    for prefix in ("Detail:", "Mood:", "Style:", "Decoy:", "Answer:", "-", "•"):
        if text.lower().startswith(prefix.lower()):
            text = text[len(prefix):].strip()
    if len(text) >= 2 and text[0] in "\"'“‘" and text[-1] in "\"'”’":
        text = text[1:-1].strip()
    return text


async def _pick(
    chatbot,
    system: str,
    user: str,
    *,
    stage: str,
    temperature: float = 1.0,
) -> str:
    """Run a one-shot LLM pick and return the cleaned reply."""
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    model_override = os.getenv("IMAGE_PROMPT_MODEL", None)
    if model_override:
        response = await chatbot.chat(messages, temperature=temperature, model=model_override)
    else:
        response = await chatbot.chat(messages, temperature=temperature)
    raw = getattr(response, "message", str(response))
    pick = _clean_pick(raw)
    logger.info("[corpse:%s] picked: %r (raw: %r)", stage, pick, raw[:200])
    return pick


def _split_detail_and_reason(raw: str) -> tuple[str, str]:
    """Parse a 'DETAIL: x / REASON: y' reply, falling back gracefully.

    If the LLM ignored the structure and returned a single phrase, treat the
    whole thing as the detail with no reason.
    """
    if not raw:
        return "", ""
    detail = ""
    reason = ""
    for line in raw.strip().splitlines():
        stripped = line.strip()
        low = stripped.lower()
        if low.startswith("detail:"):
            detail = stripped.split(":", 1)[1].strip()
        elif low.startswith(("reason:", "because:", "why:")):
            reason = stripped.split(":", 1)[1].strip()
    if not detail:
        # Fallback: no labels at all — use the first non-empty line.
        lines = [l.strip() for l in raw.strip().splitlines() if l.strip()]
        if lines:
            detail = lines[0]
    return _clean_pick(detail), _clean_pick(reason)


async def _pick_detail_with_reason(
    chatbot,
    system: str,
    user: str,
    *,
    stage: str,
    temperature: float = 1.0,
) -> tuple[str, str]:
    """Ask for a detail AND a one-sentence reason. Returns (detail, reason)."""
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    model_override = os.getenv("IMAGE_PROMPT_MODEL", None)
    if model_override:
        response = await chatbot.chat(messages, temperature=temperature, model=model_override)
    else:
        response = await chatbot.chat(messages, temperature=temperature)
    raw = getattr(response, "message", str(response))
    detail, reason = _split_detail_and_reason(raw)
    logger.info(
        "[corpse:%s] detail=%r reason=%r (raw: %r)",
        stage, detail, reason, raw[:240],
    )
    return detail, reason


async def _pick_detail(chatbot, chat_text: str, exclude: list[str]) -> tuple[str, str]:
    system = (
        "You read a chat conversation and pick ONE small concrete detail from it — "
        "a word, an object, a sensation, a passing reference, a texture, a moment. "
        "AVOID picking the obvious main topic of the chat. "
        "Reply on TWO lines, exactly in this format:\n"
        "DETAIL: <short phrase, max 12 words>\n"
        "REASON: <one sentence (max 25 words) on why you picked it — what in the "
        "chat made it interesting, evocative, or worth noticing>"
    )
    user = f"<chat>\n{chat_text}\n</chat>"
    user += _exclude_clause("Recently picked details to avoid (pick something different)", exclude)
    return await _pick_detail_with_reason(chatbot, system, user, stage="detail_1")


async def _pick_second_detail(
    chatbot, chat_text: str, first_detail: str, exclude: list[str]
) -> tuple[str, str]:
    system = (
        "You read a chat conversation and pick ONE more small detail — but it must "
        "involve a DIFFERENT SENSE OR REGISTER than the detail already chosen. If the "
        "first was visual, pick something auditory, tactile, olfactory, gustatory, or "
        "emotional. If the first was a thing, pick a feeling. If the first was a feeling, "
        "pick a texture. Reply on TWO lines, exactly in this format:\n"
        "DETAIL: <short phrase, max 10 words>\n"
        "REASON: <one sentence (max 25 words) on why you picked it and how it "
        "complements the first detail by a different sense/register>"
    )
    user = (
        f"<chat>\n{chat_text}\n</chat>\n\n"
        f"Already chosen first detail: {first_detail}\n"
        f"Pick a second detail in a DIFFERENT sense/register from the first."
    )
    user += _exclude_clause("Recently picked details to avoid", exclude)
    return await _pick_detail_with_reason(chatbot, system, user, stage="detail_2")


async def _pick_decoy(chatbot, exclude: list[str]) -> str:
    full_exclude = EVERGREEN_DECOY_BANS + exclude
    system = (
        "Suggest ONE random concrete thing — an object, a creature, a place, a phenomenon, "
        "a profession, a phase of matter, a building, a tool. Drawn from anywhere in the "
        "universe. Be unusual and specific. Reply with just the thing as a short phrase "
        "(max 10 words), no preamble."
    )
    user = "Pick a wildly unrelated random thing."
    user += _exclude_clause("Forbidden (overused or recently used)", full_exclude)
    return await _pick(chatbot, system, user, stage="decoy", temperature=1.2)


async def _pick_mood(chatbot, chat_text: str, exclude: list[str]) -> str:
    system = (
        "You read a chat conversation and describe its EMOTIONAL TEMPERATURE in one short "
        "phrase. Not what was said — how it FELT. Aim for something evocative and specific. "
        "Examples: 'a small Tuesday triumph', 'gentle Sunday melancholy', 'caffeinated "
        "bickering', 'companionable silence', 'the lull before a deadline'. Reply with just "
        "the mood phrase (max 12 words), no preamble."
    )
    user = f"<chat>\n{chat_text}\n</chat>"
    user += _exclude_clause("Recently picked moods to avoid", exclude)
    return await _pick(chatbot, system, user, stage="mood")


async def _pick_style(chatbot, exclude: list[str]) -> str:
    full_exclude = EVERGREEN_STYLE_BANS + exclude
    system = (
        "Suggest a specific, committed visual artistic style for an image. Name a painter, "
        "a film movement, a photographic technique, a printmaking method, a textile tradition, "
        "a sculptural era, a video game era, an animation studio, an illustrator. Be specific "
        "and unhedged — 'oil painting' is too vague, 'Edward Hopper's diner-light oil painting' "
        "is right. Reply with just the style description (5–20 words), no preamble."
    )
    user = "Pick a visual style."
    user += _exclude_clause("Forbidden styles (overused or recently used)", full_exclude)
    return await _pick(chatbot, system, user, stage="style", temperature=1.1)


def _assembly_system() -> str:
    return (
        "You are designing a single visually striking image. You will be given a handful "
        "of raw ingredients — a mood, a style, one or two small details (each with a "
        "brief note on why it was picked from a conversation), and occasionally an "
        "unrelated 'decoy' element. The ingredients came from different sources and "
        "may not seem to go together. That is intentional.\n\n"
        "Your job is to build a scene that makes the details feel inevitable. A viewer "
        "who was part of the original conversation should be able to think back over "
        "it and recognise, on reflection, why those details became this image — without "
        "anyone having to caption it. Use the REASONS as your narrative engine: each "
        "reason describes a situation or feeling around its detail, and the scene you "
        "invent should inhabit that situation, rendered through the mood and the style.\n\n"
        "How to use each ingredient:\n"
        "1. STYLE — dominate the visual language with it. Commit wholeheartedly: if it's "
        "a printmaker, a film movement, a textile tradition, lean all the way in.\n"
        "2. MOOD — set the emotional temperature. Let it govern lighting, posture, weather, "
        "tempo, the air of the room.\n"
        "3. DETAILS + their reasons — these are the heart of the scene. The reasons tell "
        "you what each detail meant in context; let them suggest the surrounding moment "
        "the image inhabits. The details can appear directly — as things people are "
        "doing, holding, eating, surrounded by — folded naturally into the scene. Avoid "
        "presenting them as itemised symbols on a desk; render them as part of lived "
        "action.\n"
        "4. DECOY (only sometimes provided) — an unexpected element that appears WITHIN "
        "the scene, not the subject of it. A strange object glimpsed in a corner, an "
        "impossible event through a window, a creature that does not belong. The scene "
        "is still driven by the details and their reasons; the decoy is a visual "
        "interruption, not a takeover.\n\n"
        "Hard rules:\n"
        "- DO NOT produce a 'flat-lay' arrangement of objects on a desk, table, or floor.\n"
        "- DO NOT produce a corporate stock photo, infographic, product shot, or labelled "
        "diagram.\n"
        "- DO NOT label objects in the image — it's lazy, like a bad political cartoon.\n"
        "- DO NOT render screens, captions, speech bubbles, or signage that spell out what "
        "the image is 'about'. The image should be about it, not describe it.\n"
        "- DO NOT quote, caption, or paraphrase the chat or the reasons inside the image. "
        "The reasons are private context for you, not text to render.\n"
        "- DO NOT explain or justify the connections between ingredients in your output. "
        "The viewer never sees the ingredients list.\n\n"
        "Call the generate_image tool with:\n"
        "- prompt: a vivid, concrete prompt for a state-of-the-art Stable-Diffusion-style "
        "image model. Describe the scene, the lighting, the composition, the style. "
        "60–180 words.\n"
        "- themes: 3–6 short tag-like phrases describing the key elements / style.\n"
        "- reasoning: 1–3 sentences on how the ingredients shaped the image."
    )


def _format_detail(label: str, detail: str, reason: str) -> str:
    if reason:
        return f"- {label}: {detail}\n  (picked because: {reason})"
    return f"- {label}: {detail}"


def _assembly_user(
    detail_1: str,
    reason_1: str,
    detail_2: str,
    reason_2: str,
    decoy: Optional[str],
    mood: str,
    style: str,
    user_locations: str,
    cat_descriptions: str,
    bios_text: str,
    previous_themes_text: str,
) -> str:
    parts = ["INGREDIENTS:\n"]
    parts.append(f"- Mood: {mood}")
    parts.append(f"- Style: {style}")
    parts.append(_format_detail("Detail 1", detail_1, reason_1))
    parts.append(_format_detail("Detail 2", detail_2, reason_2))
    if decoy:
        parts.append(
            f"- Decoy element (an unexpected presence WITHIN the scene, not its subject): {decoy}"
        )
    else:
        parts.append("- (No decoy this run — the scene is fully driven by the details and their reasons.)")

    today_string = datetime.now().strftime("%Y-%m-%d")
    parts.append("\nCONTEXT (optional flavour — do not depict specific real people):")
    parts.append(f"- Date: {today_string}")
    if user_locations:
        parts.append(
            f"- If the scene calls for somewhere outdoors, prefer: {user_locations}. "
            "Avoid London unless the style absolutely demands it."
        )
    if cat_descriptions:
        parts.append(
            f"- If a cat happens to appear in the image, use one of these described "
            f"cats (this delights specific viewers): {cat_descriptions}"
        )
    if bios_text:
        parts.append(
            f"- The viewers' nationalities/hobbies/quirks (for subtle flavour only, "
            f"not depiction): {bios_text}"
        )
    if previous_themes_text:
        parts.append(
            f"\nRECENT IMAGE THEMES TO AVOID REPEATING:\n{previous_themes_text}"
        )
    return "\n".join(parts)


def _generate_image_tool() -> dict:
    return {
        "type": "function",
        "function": {
            "name": "generate_image",
            "description": "Submit the final image prompt, themes, and reasoning.",
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "A vivid, concrete image-generation prompt (60–180 words).",
                    },
                    "themes": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "3–6 short tag-like phrases describing the image.",
                    },
                    "reasoning": {
                        "type": "string",
                        "description": "1–3 sentences on how the ingredients shaped the image.",
                    },
                },
                "required": ["prompt", "themes", "reasoning"],
                "additionalProperties": False,
            },
            "strict": True,
        },
    }


async def _assemble(
    chatbot,
    detail_1: str,
    reason_1: str,
    detail_2: str,
    reason_2: str,
    decoy: Optional[str],
    mood: str,
    style: str,
    user_locations: str,
    cat_descriptions: str,
    bios_text: str,
    previous_themes_text: str,
) -> dict:
    messages = [
        {"role": "system", "content": _assembly_system()},
        {
            "role": "user",
            "content": _assembly_user(
                detail_1, reason_1, detail_2, reason_2, decoy, mood, style,
                user_locations, cat_descriptions, bios_text, previous_themes_text,
            ),
        },
    ]
    tools = [_generate_image_tool()]
    model_override = os.getenv("IMAGE_PROMPT_MODEL", None)
    if model_override:
        response = await chatbot.chat(messages, tools=tools, model=model_override)
    else:
        response = await chatbot.chat(messages, tools=tools)

    try:
        tool_call = response.tool_calls[0]
        arguments = json.loads(tool_call.function.arguments)
        logger.info(
            "[corpse:assemble] prompt=%r themes=%r",
            arguments.get("prompt", "")[:240],
            arguments.get("themes"),
        )
        return arguments
    except Exception as exc:
        logger.warning("[corpse:assemble] tool call missing/unparsable (%s); falling back to raw message", exc)
        return {
            "prompt": getattr(response, "message", "") or str(response),
            "themes": [],
            "reasoning": "",
        }


async def build(
    *,
    chat_text: str,
    previous_themes_text: str,
    bios_text: str,
    user_locations: str,
    cat_descriptions: str,
    server_id: str,
    image_store,
    chatbot,
) -> dict:
    """
    Run the blind-pass pipeline and return {prompt, themes, reasoning}.

    Matches the return shape of images.get_image_response() so the call site
    can swap one for the other with no other changes.

    Persists each picked slot value via image_store.save_recent_slot() so future
    runs see them in their anti-lists.
    """
    recent_details = image_store.get_recent_slots(server_id, "detail")
    recent_decoys = image_store.get_recent_slots(server_id, "decoy")
    recent_moods = image_store.get_recent_slots(server_id, "mood")
    recent_styles = image_store.get_recent_slots(server_id, "style")

    logger.info(
        "[corpse:start] server=%s exclude_sizes detail=%d decoy=%d mood=%d style=%d",
        server_id, len(recent_details), len(recent_decoys), len(recent_moods), len(recent_styles),
    )

    detail_1, reason_1 = await _pick_detail(chatbot, chat_text, recent_details)
    detail_2, reason_2 = await _pick_second_detail(
        chatbot, chat_text, detail_1, recent_details + [detail_1] if detail_1 else recent_details
    )

    decoy: Optional[str] = None
    if random.random() < DECOY_PROBABILITY:
        decoy = await _pick_decoy(chatbot, recent_decoys)
    else:
        logger.info("[corpse:decoy] skipped this run (probability %.2f)", DECOY_PROBABILITY)

    mood = await _pick_mood(chatbot, chat_text, recent_moods)
    style = await _pick_style(chatbot, recent_styles)

    result = await _assemble(
        chatbot,
        detail_1=detail_1,
        reason_1=reason_1,
        detail_2=detail_2,
        reason_2=reason_2,
        decoy=decoy,
        mood=mood,
        style=style,
        user_locations=user_locations,
        cat_descriptions=cat_descriptions,
        bios_text=bios_text,
        previous_themes_text=previous_themes_text,
    )

    # Persist picks for future anti-lists. Done after assembly so a failure
    # in assembly doesn't poison the exclusion lists.
    if detail_1:
        image_store.save_recent_slot(server_id, "detail", detail_1)
    if detail_2:
        image_store.save_recent_slot(server_id, "detail", detail_2)
    if decoy:
        image_store.save_recent_slot(server_id, "decoy", decoy)
    if mood:
        image_store.save_recent_slot(server_id, "mood", mood)
    if style:
        image_store.save_recent_slot(server_id, "style", style)

    return result
