import os
import json
import random
from datetime import datetime


def get_initial_chat_image_prompt(chat_history: str, previous_image_themes: str, user_bios: str = "") -> str:
    user_locations = os.getenv('USER_LOCATIONS', 'the UK towns of Bath and Manchester').strip()
    cat_descriptions = os.getenv('CAT_DESCRIPTIONS', '').strip()
    today_string = datetime.now().strftime("%Y-%m-%d")
    location_guidance = ""
    if random.random() > 0.9:
        location_guidance = f"If it makes sense to use an outdoor location for the image, please choose between {user_locations}."
    cat_guidance = ""
    if cat_descriptions:
        cat_guidance = f"If cats appear in the image based on chat mentions, please use these descriptions of the actual cats owned by server members: {cat_descriptions}."
    bio_guidance = ""
    if user_bios:
        bio_guidance = f"For background colour, here are short bios of the people in the chat. Do NOT depict specific people or make the image about a specific person — but feel free to let their nationalities, hobbies, or quirks subtly flavour the mood, setting, or details of the image: {user_bios}"
    combined_chat = f"""
STEP 1 - READ AND ABSORB:
Read the entire chat history. Don't take notes. Just absorb the vibe.

STEP 2 - PICK ONE THING:
From everything you read, choose ONE single detail — the smaller
and more unexpected, the better. A texture, a mood, a passing
comment about weather, a food someone mentioned. Just one.

If nothing stands out, use the overall emotional temperature
of the day (frantic? lazy? celebratory? grumpy?).

STEP 3 - FORGET THE REST:
Seriously. Everything else from the chat — ignore it.
Do not reference it. Do not "weave it in." It's gone.

STEP 4 - MAKE ART:
Take that one detail and build a visually stunning composition
around it. You have creative freedom on style, medium, and setting.

Important: the result should be an image that makes someone smile
or pause with appreciation even if they DON'T know the context.
Think "beautiful photograph you'd hang on a wall" or "illustration
that tells a small story at a glance" — not "surrealist puzzle
that needs an artist's statement to decode."

Ground the image in something recognisable and real - the users who were having the chat should be able to look at the image and think "Ahhhh! Clever! I see what you did there!"

**Important:** If the chat history contains references to people having a truly bad time (not in jest) - please make the image cheerfull - do NOT make the user sad by reflecting their pain back to them (eg, relationship breakdown, pet or parental illness, etc).

        {location_guidance}

        {cat_guidance}

        {bio_guidance}

        {previous_image_themes}

        <chat_history>
        {chat_history}
        </chat_history>

        You **MUST** call the tool "generate_image" with the following parameters:
        - prompt: The prompt you want to give to the Stable Diffusion image model
        - themes: The themes you would use to describe the key details and artistic style in the image
        - reasoning: The reasoning you used to generate the prompt

        And remember: the prompt will be used to generate an image, so it should be clear and detailed enough for the image model to understand.
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

async def get_image_response(prompt: str, chatbot) -> dict:
    messages = [
        {"role": "user", "content": prompt}
    ]
    tools = [
        {
            "type": "function",
            "function": {
                "name": "generate_image",
                "description": "Generate an image via a Stable Diffusion model, including the prompt, themes and reasoning based on the user's request.",
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
                            "description": "The themes you would use to describe the key details and artistic style in the image"
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
    image_prompt_model = os.getenv("IMAGE_PROMPT_MODEL", None)
    if image_prompt_model:
        response = await chatbot.chat(messages, tools=tools, model=image_prompt_model)
    else:
        response = await chatbot.chat(messages, tools=tools)
    try:
        tool_call = response.tool_calls[0]
        arguments = json.loads(tool_call.function.arguments)
        return arguments
    except:
        return {"prompt": str(response), "themes": [], "reasoning": ""}
