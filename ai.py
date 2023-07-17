import os
from enum import Enum
import openai

model_name = "gpt-3.5-turbo"

class Model(Enum):
    GPT4_32k = ('gpt-4-32k', 0.03, 0.06)
    GPT4 = ('gpt-4', 0.06, 0.12)
    GPT3_5_Turbo_16k = ('gpt-3.5-turbo-16k', 0.003, 0.004)
    GPT3_5_Turbo = ('gpt-3.5-turbo', 0.0015, 0.002)

def set_api_key(api_key=""):
    openai.api_key = api_key or os.getenv("OPENAI_API_KEY", "not_set")

def get_token_price(token_count, direction="output"):
    token_price_input = 0
    token_price_output = 0
    for model in Model:
        if model_name.startswith(model.value[0]):
            token_price_input = model.value[1] / 1000
            token_price_output = model.value[2] / 1000
            break
    if direction == "input":
        return round(token_price_input * token_count, 4)
    return round(token_price_output * token_count, 4)

def get_image_price(size="512x512"):
    if size == "1024x1024":
        return 0.020
    if size == "512x512":
        return 0.018
    if size == "256x256":
        return 0.016
    raise Exception("Invalid image size")

async def chat(question, context, temperature=0.9, max_tokens=1024):
    if not openai.api_key:
        set_api_key()
    if type(context) == list:
        messages = context
        messages.append({
            "role": "user",
            "content": question,
        })
    elif type(context) == str:
        messages = [{
            "role": "user",
            "content": context,
        }, {
            "role": "user",
            "content": question,
        }]
    else:
        raise Exception("Context must be a list or a string")

    response = openai.ChatCompletion.create(
        model=model_name,
        messages=messages,
        temperature=float(temperature),
        max_tokens=max_tokens,
    )

    tokens = response['usage']['total_tokens']
    cost = get_token_price(tokens)
    reply = response['choices'][0]['message']['content']

    return reply, tokens, cost

async def image(prompt, size="512x512", format="url"):
    if not openai.api_key:
        set_api_key()

    response = openai.Image.create(
        prompt=prompt,
        n=1,
        size=size,
        response_format=format,
    )

    field = "b64_json" if format == "b64_json" else "url"
    return response['data'][0][field], 0, get_image_price(size)
