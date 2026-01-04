import requests
import os

async def search(query: str) -> str:
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
    formatted_response = f"{decoded_response['choices'][0]['message']['content']}\n\n**Sources:**\n"

    for source in decoded_response['search_results']:
        formatted_response += f"- <{source['url']}>\n"

    return formatted_response[:1800]
