import logging

from litellm import acompletion

logger = logging.getLogger(__name__)


async def search(query: str) -> str:
    """
    Search Twitter/X via Grok's built-in Twitter access.

    Grok has native access to Twitter/X data - we just ask it naturally
    without defining any tools. It will search and return relevant tweets.

    Args:
        query: The search query for Twitter

    Returns:
        Formatted response with Twitter content (max ~1800 chars)
    """
    logger.info(f"[GROK/TWITTER] Starting Twitter/X search with query: {query}")

    try:
        response = await acompletion(
            model="openrouter/x-ai/grok-4.1-fast",
            messages=[
                {
                    "role": "system",
                    "content": "You have access to real-time Twitter/X data. Search Twitter and respond very concisely - your response will be sent to a Discord server so you only have about 1800 characters. Include usernames and paraphrase key tweets. Format as a brief summary with bullet points for individual tweets."
                },
                {
                    "role": "user",
                    "content": f"Search Twitter/X for: {query}"
                }
            ]
            # No tools needed - Grok has built-in Twitter access
        )

        logger.info(f"[GROK/TWITTER] Received response from model: {getattr(response, 'model', 'unknown')}")

        content = response.choices[0].message.content or ""
        logger.info(f"[GROK/TWITTER] Message content: {content[:200] if content else '(empty)'}...")

        if not content:
            logger.warning("[GROK/TWITTER] Empty response from Grok")
            return "No Twitter results found."

        logger.info(f"[GROK/TWITTER] Returning response of {len(content)} chars")
        return content[:1800]

    except Exception as e:
        logger.error(f"[GROK/TWITTER] Error during search: {type(e).__name__}: {e}")
        return f"Sorry, Twitter search failed: {e}"
