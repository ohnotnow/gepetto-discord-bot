from litellm import acompletion

async def websearch(query: str, search_context_size: str = "medium"):
    response = await acompletion(
        model="openai/gpt-4o-mini-search-preview",
        messages=[
            {
                "role": "user",
                "content": query,
            }
        ],
        web_search_options={
            "search_context_size": "medium"  # Options: "low", "medium", "high"
        }
    )
    return response.choices[0].message.content[:1800]
