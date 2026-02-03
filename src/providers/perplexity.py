import logging
import os

import requests

logger = logging.getLogger(__name__)


async def search(query: str) -> str:
    logger.info(f"[PERPLEXITY] Starting web search with query: {query}")

    url = "https://api.perplexity.ai/chat/completions"

    payload = {
        "model": "sonar",
        "messages": [
            {"role": "system", "content": "Please respond very concisely.  Your response will be sent to a discord server so you only have about 1800 characters in total."},
            {"role": "user", "content": query}
        ],
        "web_search_options": {
            "search_context_size": "low",
        }
    }

    headers = {
        "Authorization": f"Bearer {os.getenv('PERPLEXITY_API_KEY')}",
        "Content-Type": "application/json"
    }

    response = requests.post(url, json=payload, headers=headers)
    decoded_response = response.json()

    logger.info(f"[PERPLEXITY] Received response from model: {decoded_response.get('model', 'unknown')}")

    formatted_response = f"{decoded_response['choices'][0]['message']['content']}\n\n**Sources:**\n"

    sources = decoded_response.get('search_results', [])
    logger.info(f"[PERPLEXITY] Response includes {len(sources)} sources")

    for source in sources:
        formatted_response += f"- <{source['url']}>\n"

    logger.info(f"[PERPLEXITY] Returning response of {len(formatted_response)} chars")
    return formatted_response[:1800]
