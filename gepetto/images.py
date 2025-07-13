import os
import json
import random
from datetime import datetime
import google.generativeai as genai
from google.ai.generativelanguage_v1beta.types import content

def get_initial_chat_image_prompt(chat_history: str, previous_image_themes: str) -> str:
    user_locations = os.getenv('USER_LOCATIONS', 'the UK towns of Bath and Manchester').strip()
    today_string = datetime.now().strftime("%Y-%m-%d")
    location_guidance = ""
    if random.random() > 0.9:
        location_guidance = f"If it makes sense to use an outdoor location for the image, please choose between {user_locations}."
    combined_chat = f"""
        You are tasked with creating a visually remarkable Stable Diffusion prompt for a Discord server of software developers.

        STEP 1 - DELIBERATELY AVOID THE OBVIOUS:
        First, identify the main conversation topics (likely tech/work related) and keep them at the back of your mind.  These are the obvious topics - we want to be surprising and creating!

        STEP 2 - HUNT FOR THE PERIPHERAL:
        Scan for brief, casual mentions of:
        - Physical sensations (tired, hungry, cold, comfortable)
        - Environmental details (weather, sounds, lighting, time of day)
        - Passing references to objects, food, animals, or places
        - Emotional micro-moments (small frustrations, tiny celebrations)
        - Background activities or interruptions
        - Sensory experiences or textures mentioned
        - If you are using the main themes - be subtle, be creative, work them into some other details you have identified.
        - DO NOT invent any details, only use the ones that are mentioned in the chat history.

        STEP 3 - ARTISTIC STYLE SELECTION:
        Choose your visual approach from the broad world of art:
        - Classical fine art tradition (oil painting, watercolor, etc.)
        - Photography genres (portrait, landscape, street photography, macro)
        - Illustration styles (vintage poster, children's book, technical drawing)
        - Abstract or experimental approaches
        - Historical art movements (impressionist, art nouveau, minimalist)
        - Cinematography (film noir, horror, etc.)

        STEP 4 - AMPLIFY THE SUBTLE:
        Take your chosen peripheral detail and make it the HERO of a visually stunning composition. Think about:
        - What mood or atmosphere does this detail suggest?
        - What unexpected artistic style would make this mundane detail fascinating?
        - How can you create visual drama from something small?

        GUIDELINES:
        - Software developers love wit and unexpected connections
        - Create something visually striking that would make them pause and smile
        - Avoid cyberpunk entirely
        - The prompt should be detailed enough for Stable Diffusion
        - If today's date ({today_string}) has UK significance, weave it in naturally
        - Surprise them with creative interpretations they wouldn't expect

        {location_guidance}

        {previous_image_themes}

        Respond with JSON:
        {{
            "prompt": "Your detailed Stable Diffusion prompt here",
            "themes": ["the subtle details you focused on"],
            "reasoning": "Brief explanation of your creative choice"
        }}
        """
    return combined_chat


def get_extra_guidelines() -> str:
    extra_guidelines = ""
    random_1 = random.random()
    random_2 = random.random()
    random_3 = random.random()
    if random_2 > 0.9:
        if random.random() > 0.9:
            extra_guidelines += "- The image should be in the style of a medieval painting.\n"
        elif random.random() > 0.8:
            extra_guidelines += "- The image should be in the style of a 1950s budget sci-fi movie poster.\n"
        elif random.random() > 0.7:
            extra_guidelines += "- The image should echo the style of De Chirico.\n"
        elif random.random() > 0.6:
            extra_guidelines += "- The image should echo the style of Hieronymus Bosch.\n"
        elif random.random() > 0.5:
            extra_guidelines += "- The image should be in the style of a 1970s horror film poster.\n"
        elif random.random() > 0.4:
            extra_guidelines += "- The image should look like a still from a 1970s low-budget adult film that has been badly transferred to VHS.\n"
        elif random.random() > 0.3:
            extra_guidelines += "- Ideally echo the style of Eduard Munch.\n"
        elif random.random() > 0.5:
            extra_guidelines += f"- The image should be in the style of a instagram post IMG_{int(random.random() * 1000)}.CR2.\n"
    if random_3 > 0.9:
        visual_choice = random.random()
        if visual_choice > 0.7:
            extra_guidelines += "- The image should be wildly colourful, surreal and mind-bending.\n"
        elif visual_choice > 0.4:
            extra_guidelines += "- The image should be a single object, such as a vase or a teacup.\n"
        elif visual_choice > 0.2:
            extra_guidelines += "- The image should be in the style of a 1980s computer game.\n"
        else:
            extra_guidelines += "- Please make the image a little bit like a famous painting.\n"
    if random_1 > 0.9:
        if random.random() > 0.5:
            extra_guidelines += "\n- If you can somehow shoehorn a grotesque reference to UK Politician Liz Truss into the image, please do so.\n"
        if random.random() > 0.5:
            extra_guidelines += "\n- The image should be set in a Pork Market.\n"
        if random.random() > 0.5:
            extra_guidelines += "\n- The image should be reflective of a blood-curdling, gory, horror film.\n"
    return extra_guidelines

async def get_image_response_from_llm(prompt: str, chatbot) -> str:
    return await get_image_response(prompt, chatbot)

async def get_image_response(prompt: str, chatbot) -> dict:
    messages = [
        {"role": "user", "content": prompt}
    ]
    tools = [
        {
            "type": "function",
            "function": {
                "name": "get_image_response",
                "description": "Generate a Stable Diffusion image prompt, themes and reasoning based on the user's request.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "prompt": {
                            "type": "string",
                            "description": "The prompt you want to give to the Stable Diffusion image model"
                        },
                        "themes": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "The themes you want to use in the image"
                        },
                        "reasoning": {
                            "type": "string",
                            "description": "The reasoning you used to generate the prompt"
                        }
                    },
                    "required": ["prompt", "themes", "reasoning"],
                    "additionalProperties": False
                },
                "strict": True
            }
        }
    ]
    response = await chatbot.chat(messages, tools=tools)
    tool_call = response.tool_calls[0]
    arguments = json.loads(tool_call.function.arguments)
    return arguments

async def get_image_response_from_gemini(prompt: str) -> dict:
    genai.configure(api_key=os.environ["GEMINI_API_KEY"])

    generation_config = {
        "temperature": 1.5,
        "top_p": 0.95,
        "top_k": 40,
        "max_output_tokens": 8192,
        "response_schema": content.Schema(
            type = content.Type.OBJECT,
            enum = [],
            required = ["prompt", "themes", "reasoning"],
            properties = {
                "prompt": content.Schema(
                    type = content.Type.STRING,
                ),
                "themes": content.Schema(
                    type = content.Type.ARRAY,
                    items = content.Schema(
                    type = content.Type.STRING,
                    ),
                ),
                "reasoning": content.Schema(
                    type = content.Type.STRING,
                ),
            },
        ),
        "response_mime_type": "application/json",
    }

    model = genai.GenerativeModel(
        model_name="gemini-2.0-flash",
        generation_config=generation_config,
    )

    chat_session = model.start_chat(
        history=[
            {
                "role": "user",
                "parts": [
                    prompt,
                ],
            },
        ],
    )

    response = chat_session.send_message(prompt)

    return json.loads(response.text)

if __name__ == "__main__":
    chat_history = """
    Hello, how are you?

    I am good, thank you.
    """

    print(get_image_response_from_llm("gemini", get_initial_chat_image_prompt(chat_history, "")))
