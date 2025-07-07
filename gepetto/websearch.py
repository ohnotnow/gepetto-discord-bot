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
    response_text = response.choices[0].message.content
    response = await acompletion(
        model="openai/gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": "You are a helpful assistant that summarises the web search results for the user. You MUST keep the markdown links to the sources, but give a concise summary of the text around them.  Your response will be sent to a discord server so you only have about 1800 characters in total.",
            },
            {
                "role": "user",
                "content": response_text,
            }
        ]
    )
    return response.choices[0].message.content[:1800]
