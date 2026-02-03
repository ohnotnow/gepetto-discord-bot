import logging
import os
import re

from xai_sdk import Client
from xai_sdk.chat import user
from xai_sdk.tools import x_search

logger = logging.getLogger(__name__)


def _format_for_discord(content: str, citations: list | None) -> str:
    """
    Format response for Discord:
    - Remove excessive whitespace
    - Convert @username to <https://x.com/username>
    - Wrap URLs in angle brackets to prevent previews
    - Add top citations
    - Truncate to ~1800 chars
    """
    # Collapse multiple newlines into max 2 (one blank line)
    content = re.sub(r'\n{3,}', '\n\n', content)

    # Remove trailing whitespace on each line
    content = re.sub(r'[ \t]+\n', '\n', content)

    # Remove leading/trailing whitespace
    content = content.strip()

    # Convert @mentions to x.com links (but not email-like patterns)
    # Match @username that's not preceded by alphanumeric (to avoid emails)
    content = re.sub(
        r'(?<![a-zA-Z0-9])@([a-zA-Z0-9_]+)',
        r'<https://x.com/\1>',
        content
    )

    # Wrap any remaining bare URLs in angle brackets
    # Match http(s) URLs not already wrapped in < >
    content = re.sub(
        r'(?<![<])(https?://[^\s\)>\]]+)',
        r'<\1>',
        content
    )

    # Add top citations if available
    if citations and len(citations) > 0:
        content += "\n**Sources:**\n"
        for url in citations[:5]:
            content += f"- <{url}>\n"

    return content[:1800]


async def search(query: str) -> str:
    """
    Search Twitter/X via xAI SDK with server-side x_search tool.

    Uses Grok's native Twitter access to search for real-time posts.

    Args:
        query: The search query for Twitter

    Returns:
        Formatted response with Twitter content (max ~1800 chars)
    """
    logger.info(f"[GROK/TWITTER] Starting Twitter/X search with query: {query}")

    api_key = os.getenv("XAI_API_KEY")
    if not api_key:
        logger.error("[GROK/TWITTER] XAI_API_KEY not set")
        return "Twitter search not configured (missing XAI_API_KEY)"

    try:
        client = Client(api_key=api_key)

        chat = client.chat.create(
            model="grok-4-1-fast",
            tools=[x_search()],
        )

        # Add the user query with instructions for concise output
        chat.append(user(
            f"Search Twitter/X for: {query}\n\n"
            "Be very concise - max 1500 characters. "
            "List key tweets with @usernames and brief summaries. "
            "Focus on the most recent and relevant posts."
        ))

        # Collect the full response (non-streaming collection)
        full_content = ""
        tool_calls_made = []
        response = None

        for response, chunk in chat.stream():
            # Track tool calls for logging
            for tool_call in chunk.tool_calls:
                tool_calls_made.append(f"{tool_call.function.name}")

            # Collect content
            if chunk.content:
                full_content += chunk.content

        logger.info(f"[GROK/TWITTER] Tools used: {tool_calls_made}")
        logger.info(f"[GROK/TWITTER] Raw content length: {len(full_content)} chars")

        if not full_content:
            logger.warning("[GROK/TWITTER] Empty response from Grok")
            return "No Twitter results found."

        # Get citations from final response
        citations = response.citations if response else None
        if citations:
            logger.info(f"[GROK/TWITTER] Got {len(citations)} citations")

        # Format for Discord
        formatted = _format_for_discord(full_content, citations)
        logger.info(f"[GROK/TWITTER] Returning formatted response of {len(formatted)} chars")

        return formatted

    except Exception as e:
        logger.error(f"[GROK/TWITTER] Error during search: {type(e).__name__}: {e}")
        return f"Sorry, Twitter search failed: {e}"
