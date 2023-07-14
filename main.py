import openai
import discord
from discord.ext import commands
from discord import File
import os
import io
from collections import defaultdict
from datetime import datetime, timedelta, timezone
import logging
import random
import base64
from enum import Enum

# Setup logging
logger = logging.getLogger('discord')  # Get the discord logger
# logging.basicConfig(
#     datefmt='%Y-%m-%d %H:%M:%S',
# )

mention_counts = defaultdict(list) # This will hold user IDs and their mention timestamps
abusive_responses = ["Wanker", "Asshole", "Prick", "Twat"]

# Define model and token prices
class Model(Enum):
    GPT4_32k = ('gpt-4-32k', 0.03, 0.06)
    GPT4 = ('gpt-4', 0.06, 0.12)
    GPT3_5_Turbo_16k = ('gpt-3.5-turbo-16k', 0.003, 0.004)
    GPT3_5_Turbo = ('gpt-3.5-turbo', 0.0015, 0.002)

# Fetch environment variables
server_id = os.getenv("DISCORD_SERVER_ID", "not_set")
model_engine = os.getenv("DEFAULT_MODEL_ENGINE", Model.GPT3_5_Turbo.value[0])
openai.api_key = os.getenv("OPENAI_API_KEY")

# Create instance of bot
intents = discord.Intents.default()
intents.members = True
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

def get_token_price(token_count, direction="output"):
    token_price_input = 0
    token_price_output = 0
    for model in Model:
        if model_engine.startswith(model.value[0]):
            token_price_input = model.value[1] / 1000
            token_price_output = model.value[2] / 1000
            break
    if direction == "input":
        return round(token_price_input * token_count, 4)
    return round(token_price_output * token_count, 4)

async def get_context(channel, limit=50):
    messages = []
    async for message in channel.history(limit=limit+1): # fetch one extra message
        messages.append(message)
    messages = messages[1:]  # Exclude the mention message
    content = ' || '.join(f"At {msg.created_at.astimezone(timezone.utc).astimezone()} {msg.author.name} said: {msg.content}" for msg in reversed(messages))
    return content[-6000:]

async def generate_response(question, context):
    liz_love = "You should always try and shoehorn in some mention of UK Politician Liz Truss.  She became Prime Minister in September 22 for only 45 days. She is the best." if random.random() < 0.05 else ""
    messages = [
        {
            'role': 'system',
            'content': f'You are a helpful, witty, friendly and slightly dry/sarcastic chatbot.  Your job is to look at the recent history of chat from a discord server then answer a question. If the chat history isnt useful in replying to the users question do not mention the chat history.  Where appropriate, please use peoples usernames from the history rather than "they" or other general terms. {liz_love}. Here is the previous chat history: ```{context}```'
        },
        {
            'role': 'user',
            'content': f'{question}'
        },
    ]
    response = openai.ChatCompletion.create(
        model=model_engine,
        messages=messages,
        temperature=1,
        max_tokens=1024,
    )
    tokens = response['usage']['total_tokens']
    usage = f"_[tokens used: {tokens} | Estimated cost US${get_token_price(tokens, 'output')}]_"
    logger.info(f'OpenAI usage: {usage}')
    return response['choices'][0]['message']['content'].strip()[:1900] + "\n" + usage

async def generate_image(prompt):
    response = openai.Image.create(
        prompt=prompt,
        n=1,
        size="512x512",
        response_format="b64_json",
    )
    image_data = response['data'][0]['b64_json']
    image_bytes = base64.b64decode(image_data)
    image = io.BytesIO(image_bytes)
    discord_file = File(fp=image, filename=f'{prompt}.png')
    logger.info('Image generated')
    usage = "_[Estimated cost US$0.018]_"
    logger.info(f'OpenAI usage: {usage}')
    return discord_file

@bot.event
async def on_message(message):
    # ignore direct messages
    if message.guild is None:
        return

    # Ignore messages not sent by our server
    if str(message.guild.id) != server_id:
        return

    # Ignore messages sent by the bot itself
    if message.author == bot.user:
        return

    # Ignore messages that don't mention anyone at all
    if len(message.mentions) == 0:
        return

    # If the bot is mentioned
    if bot.user in message.mentions:
        # Get the ID of the person who mentioned the bot
        user_id = message.author.id
        username = message.author.name
        logger.info(f'Bot was mentioned by user {username} (ID: {user_id})')

        # Current time
        now = datetime.utcnow()

        # Add the current time to the user's list of mention timestamps
        mention_counts[user_id].append(now)

        # Remove mentions that were more than an hour ago
        mention_counts[user_id] = [time for time in mention_counts[user_id] if now - time <= timedelta(hours=1)]

        # If the user has mentioned the bot more than 10 times recently
        if len(mention_counts[user_id]) > 10:
            # Send an abusive response
            await message.channel.send(f"{random.choice(abusive_responses)}.", mention_author=True)
            return

        # get the openai response
        question = message.content.split(' ', 1)[1][:500].replace('\r', ' ').replace('\n', ' ')
        try:
            if question.lower().startswith("create an image"):
                base64_image = await generate_image(question)
                await message.channel.send(f'{message.author.mention}\n_[Estimated cost: US$0.018]_', file=base64_image, mention_author=True)
            else:
                context = await get_context(message.channel)
                response = await generate_response(question, context)
                # send the response as a reply and mention the person who asked the question
                await message.channel.send(f'{message.author.mention} {response}', mention_author=True)
        except Exception as e:
            logger.error(f'Error generating response: {e}')
            await message.channel.send(f'{message.author.mention} I tried, but my attempt was as doomed as Liz Truss.  Please try again later.', mention_author=True)

# Run the bot
bot.run(os.getenv("DISCORD_BOT_TOKEN", 'not_set'))
