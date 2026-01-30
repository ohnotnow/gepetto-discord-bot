"""
Memory extraction from chat history.
"""
import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Category -> expiration days mapping
CATEGORY_EXPIRY = {
    'health_temporary': 7,
    'pet_new': 30,
    'relationship': 14,
    'travel': 7,
    'work': 30,
    'interest': None,  # Goes to bio instead
    'general': 14,
}

EXTRACTION_PROMPT = '''Analyze these Discord chat messages and extract interesting personal facts about users.
Focus on things that are unusual, specific, or personal - NOT generic conversation.

Good examples of things to extract:
- "just got a new kitten named Whiskers" (pet_new)
- "has a cold this week" (health_temporary)
- "started a new job at a startup" (work)
- "is German, lives in Madrid" (interest -> becomes bio)
- "broke up with partner" (relationship)
- "going on holiday to Spain next week" (travel)

Bad examples (too generic, skip these):
- "said hello" or "asked a question"
- "likes pizza" (too common/generic)
- Things that are obviously jokes or sarcasm

For each fact, categorize it:
- health_temporary: illness, injury (temporary conditions)
- pet_new: new pet arrival
- relationship: breakup, new partner, engagement, etc
- travel: on holiday, visiting somewhere
- work: job changes, work events, career news
- interest: long-term traits, heritage, location, hobbies (these become bio updates)
- general: other interesting facts that don't fit above

Return valid JSON with this structure:
{
    "memories": [
        {"user_id": "discord_user_id", "user_name": "display_name", "memory": "the fact in third person", "category": "category_name"}
    ],
    "bio_updates": [
        {"user_id": "discord_user_id", "user_name": "display_name", "bio_addition": "long-term trait or fact"}
    ]
}

If nothing interesting, return: {"memories": [], "bio_updates": []}

Important:
- Write memories in third person ("has a cold" not "I have a cold")
- Only extract facts you're confident about
- bio_updates are for long-term stable facts (heritage, location, career type)
- memories are for time-limited facts (illness, travel, recent events)'''


async def extract_memories_from_history(
    chatbot,
    messages: List[Dict[str, Any]],
    existing_bio: Optional[str] = None
) -> Dict[str, Any]:
    """
    Analyze chat messages and extract interesting user facts.

    Args:
        chatbot: LLM provider instance for extraction
        messages: List of message dicts with 'author_id', 'author_name', 'content'
        existing_bio: Current bio text to update (if any)

    Returns:
        {
            "memories": [
                {
                    "user_id": "123",
                    "user_name": "Alice",
                    "memory": "just got a new kitten named Whiskers",
                    "category": "pet_new"
                },
                ...
            ],
            "bio_updates": [
                {
                    "user_id": "123",
                    "user_name": "Alice",
                    "bio_addition": "has a cat named Whiskers"
                },
                ...
            ]
        }
    """
    empty_result = {"memories": [], "bio_updates": []}

    if not messages:
        return empty_result

    # Format messages for the LLM
    formatted_messages = []
    for msg in messages:
        author_id = msg.get('author_id', 'unknown')
        author_name = msg.get('author_name', 'unknown')
        content = msg.get('content', '')
        formatted_messages.append(f"[{author_name} (id:{author_id})]: {content}")

    chat_text = "\n".join(formatted_messages)

    bio_context = ""
    if existing_bio:
        bio_context = f"\n\nExisting bio information (update/merge if new info): {existing_bio}"

    llm_messages = [
        {
            'role': 'system',
            'content': EXTRACTION_PROMPT
        },
        {
            'role': 'user',
            'content': f"Here are the chat messages to analyze:{bio_context}\n\n{chat_text}"
        }
    ]

    try:
        response = await chatbot.chat(
            messages=llm_messages,
            temperature=0.3,  # Lower temperature for more consistent extraction
            json_mode=True
        )

        result = json.loads(response.message)

        # Validate structure
        if not isinstance(result, dict):
            logger.warning("Memory extraction returned non-dict result")
            return empty_result

        memories = result.get("memories", [])
        bio_updates = result.get("bio_updates", [])

        # Validate memories have required fields
        valid_memories = []
        for mem in memories:
            if all(k in mem for k in ['user_id', 'user_name', 'memory', 'category']):
                valid_memories.append(mem)
            else:
                logger.warning(f"Skipping malformed memory: {mem}")

        # Validate bio_updates have required fields
        valid_bio_updates = []
        for bio in bio_updates:
            if all(k in bio for k in ['user_id', 'user_name', 'bio_addition']):
                valid_bio_updates.append(bio)
            else:
                logger.warning(f"Skipping malformed bio_update: {bio}")

        return {
            "memories": valid_memories,
            "bio_updates": valid_bio_updates
        }

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse extraction response as JSON: {e}")
        return empty_result
    except Exception as e:
        logger.error(f"Memory extraction failed: {e}")
        return empty_result


def get_expiry_for_category(category: str) -> Optional[datetime]:
    """Get expiration datetime for a category, or None if permanent."""
    days = CATEGORY_EXPIRY.get(category, 14)
    if days is None:
        return None
    return datetime.now() + timedelta(days=days)
