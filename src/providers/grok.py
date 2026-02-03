import logging

from litellm import acompletion

logger = logging.getLogger(__name__)

# Grok x_search tool definition - passed to Grok so it executes the search server-side
X_SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "x_search",
        "description": "Search X (Twitter) for real-time posts and discussions",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query for X"
                }
            },
            "required": ["query"]
        }
    }
}


async def search(query: str) -> str:
    """
    Search Twitter/X via Grok x_search tool.

    Args:
        query: The search query for Twitter

    Returns:
        Formatted response with content and citations (max ~1800 chars)
    """
    logger.info(f"[GROK/TWITTER] Starting Twitter/X search with query: {query}")

    response = await acompletion(
        model="openrouter/x-ai/grok-4.1-fast",
        messages=[
            {
                "role": "system",
                "content": "Please respond very concisely. Your response will be sent to a Discord server so you only have about 1800 characters in total. Include relevant tweet URLs as citations."
            },
            {
                "role": "user",
                "content": query
            }
        ],
        tools=[X_SEARCH_TOOL]
    )

    logger.info(f"[GROK/TWITTER] Received response from model: {response.model}")

    content = response.choices[0].message.content or ""

    # Handle citations if present (Grok returns these in the response)
    citations = getattr(response, "citations", None)
    if citations:
        logger.info(f"[GROK/TWITTER] Response includes {len(citations)} citations")
        content += "\n\n**Sources:**\n"
        for url in citations[:5]:  # Limit to 5 citations
            content += f"- <{url}>\n"
    else:
        logger.info("[GROK/TWITTER] No citations in response")

    logger.info(f"[GROK/TWITTER] Returning response of {len(content)} chars")
    return content[:1800]
