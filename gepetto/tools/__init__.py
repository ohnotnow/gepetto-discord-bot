tool_list = [
    {
        "type": "function",
        "function": {
            "name": "get_weather_forecast",
            "description": "Gets a weather forecast based on the user prompt. The prompt should contain the user's full request, and the function will extract relevant details from it.",
            "parameters": {
                "type": "object",
                "properties": {
                "prompt": {
                    "type": "string",
                    "description": "The full user prompt containing their request for the weather forecast."
                },
                "locations": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "description": "The UK town or city where the weather forecast is requested."
                    },
                    "description": "An array of UK towns or cities where the weather forecast is requested."
                }
            },
            "required": ["prompt", "location"]
        }
    }
},
{
    "type": "function",
    "function": {
        "name": "create_image",
        "description": "Generates an image based on the user's prompt. This should be used when the user requests something like 'create an image of...', 'paint a picture', or includes emojis suggesting a picture or camera.",
        "parameters": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "The user's full prompt specifying the image they want to generate, including any flags or modifiers they gave (eg, --better or --artstyle <style>)."
                }
            },
            "required": ["prompt"]
        }
    }
},
{
    "type": "function",
    "function": {
        "name": "summarise_webpage_content",
        "description": "Summarizes the content of a webpage based on the provided URL and prompt. This tool should be used when the user requests a summary and includes a URL in their prompt, or uses an emoji like 👀 to indicate they want a summary of the page.",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The URL of the webpage to summarize."
                },
                "prompt": {
                    "type": "string",
                    "description": "The user's prompt requesting the summary, with the URL removed."
                }
            },
            "required": ["url", "prompt"]
        }
    }
},
{
    "type": "function",
    "function": {
        "name": "extract_recipe_from_webpage",
        "description": "Extracts a list of ingredients and steps for a recipe from a webpage if the user provided a URL and recipe-related question.",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The user-provided URL of the webpage containing the recipe."
                },
                "prompt": {
                    "type": "string",
                    "description": "The user's prompt requesting the recipe, with the URL removed."
                }
            },
            "required": ["url", "prompt"]
            }
        }
    }
]
