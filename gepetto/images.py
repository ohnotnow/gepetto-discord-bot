import os
import random
from datetime import datetime
def get_initial_chat_image_prompt(chat_history: str, previous_image_themes: str) -> str:
    user_locations = os.getenv('USER_LOCATIONS', 'the UK towns of Bath and Manchester').strip()
    today_string = datetime.now().strftime("%Y-%m-%d")
    location_guidance = ""
    if random.random() > 0.9:
        location_guidance = f"8. If it makes sense to use an outdoor location for the image, please choose between {user_locations}."
    combined_chat = f"""
You will be given a Discord server transcript between UK-based Caucasian adult male IT workers.  Please do not misgender or
misethnicise them.

<chat-history>
{chat_history}
</chat-history>

1. Identify 1-3 themes from the conversation which would be good to visualise and bring delight to the users.  These can be literal important themes, or a more subtle play on words referencing the themes.
2. Create a descriptive and creative image prompt for a Stable Diffusion image model that incorporates the chosen theme(s).  It should
capture the essence of the conversation themes and be a unique and artistic interpretation.  It could be a literal, or an abstract, or a comedic, or... representation of the theme(s).
3. The users work as software developers, so they delight in clever and witty puns, wordplay and references.  You should delight in them too!
4. The image should be visually interesting and appealing.
5. You could choose a single artistic movement from across the visual arts, historic or modern, to inspire the image - cinematic, film noir, sci-fi, modernist, surrealist, anime, charcoal illustration - the world is your oyster!
6. The prompt should be highly detailed and imaginative, as suits a Stable Diffusion image model.
7. If todays date ({today_string}) seems significant to people in the UK, please use it in your prompt.
{location_guidance}

{previous_image_themes}

Examples of good Stable Diffusion model prompts :

"a beautiful and powerful mysterious sorceress, smile, sitting on a rock, lightning magic, hat, detailed leather clothing with gemstones, dress, castle background, digital art, hyperrealistic, fantasy, dark art, artstation, highly detailed, sharp focus, sci-fi, dystopian, iridescent gold, studio lighting"

"Moulin Rouge, cabaret style, burlesque, photograph of a gorgeous beautiful woman, slender toned body, at a burlesque club, highly detailed, posing, smoky room, dark lit, low key, alluring, seductive, muted colors, red color pop, rim light, lingerie, photorealistic, shot with professional DSLR camera, F1. 4, 1/800s, ISO 100, sharp focus, depth of field, cinematic composition"

"A portrait of a woman with horns, split into two contrasting halves. One side is grayscale with intricate tattoos and a serious expression, while the other side is in vivid colors with a more intense and fierce look. The background is divided into gray and red, enhancing the contrast between the two halves. The overall style is edgy and artistic, blending elements of fantasy and modern tattoo art."

"A candid photograph of a beautiful woman, looking away from the viewer, long straight dark blonde hair, light blue eyes, fair complexion, full lips, sitting in a comfy chair, looking out the window, snowing outside, wearing nothing, covered in a thin blanket, showing some cleavage, enjoying the view"

"A verification selfie webcam pic of an attractive woman smiling. Holding up a sign written in blue ballpoint pen that says "KEEP THINGS REAL" on an crumpled index card with one hand. Potato quality. Indoors, night, Low light, no natural light. Compressed. Reddit selfie. Low quality."

"Evening Love Song. Ornamental clouds.compose an evening love song;.a road leaves evasively..The new moon begins.a new chapter of our nights,.of those frail nights.we stretch out and which mingle.with these black horizontals...by Posuka Demizu, Arthur Rackham and Tony DiTerlizzi, meticulous, intricate, entangled, intricately detailed"

Please respond with the following JSON object with the prompt for the Stable Diffusion image model and the themes you identified.

{{
    "prompt": "Your stable diffusion prompt here",
    "themes": ["theme1", ...],
    "reasoning": "Your reasoning for choosing the themes and prompt"
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
