from litellm import acompletion

async def websearch(query: str, search_context_size: str = "medium"):
    search_prompt = f"""
        Please give *very* succinct web search results for the following query (no more than one or two sentences per source).
        Your response will be sent to a discord server so you only have about 1800 characters in total.
        Use plain discord formatting around the links to the sources so they do not generate a preview - do not use markdown links, eg:
        Good: <https://www.google.com>
        Bad: [https://www.google.com](https://www.google.com)

        The query is:
        <user_query>
        {query}
        </user_query>
    """
    response = await acompletion(
        model="openai/gpt-4o-mini-search-preview",
        messages=[
            {
                "role": "user",
                "content": search_prompt,
            }
        ],
        web_search_options={
            "search_context_size": "medium"  # Options: "low", "medium", "high"
        }
    )
    return response.choices[0].message.content[:1800]
