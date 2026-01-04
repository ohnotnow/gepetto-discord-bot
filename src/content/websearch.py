from litellm import acompletion
import re

def fix_discord_links(text: str) -> str:
    # 1. Replace markdown links [text](url) with <url>
    text = re.sub(r'\[.*?\]\((https?://[^\s)]+)\)', r'<\1>', text)

    # 2. Replace bare URLs with <url>, but not if they're already inside <>
    # This regex finds http(s) links NOT immediately preceded by < and NOT followed by >
    text = re.sub(
        r'(?<!<)(https?://[^\s>]+)(?!>)',
        r'<\1>',
        text
    )
    text = text.replace("?utm_source=openai", "")
    return text

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

        Remember - the angle brackets around the links are important!
        **Do not use markdown formatting for the links and do not use plain text!**
        Otherwise discord will generate a preview for every link and fill the users screen with annoying previews!

        Your response should be a concise summary of the search results followed by the list of links to the sources.  If there
        are duplicate sources you should only include them once.
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
            "search_context_size": "low"  # Options: "low", "medium", "high"
        }
    )

    response_text = response.choices[0].message.content

    summary_response = await acompletion(
        model="openai/gpt-4o-mini",
        messages=[
            {
                "role": "user",
                "content": f"Please give a concise summary of the following web search results.  Your response will be sent to a discord server so you only have about 1800 characters in total.  **YOU MUST KEEP THE LINKS TO THE SOURCES IN YOUR SUMMARY - THIS IS CRITICAL!!**. If there are more than five sources, you should give a summary of the most important ones with their sources, then just summarise all the rest without their sources.  The web search results are: {response_text}",
            }
        ]
    )

    summary_text = summary_response.choices[0].message.content
    return fix_discord_links(summary_text)[:1800]
