import logging
import random
import json
import re
from constants import abusive_responses
from utils import truncate
from gepetto.helpers.history import get_history_as_openai_messages, build_messages
from gepetto import guard, gpt, mistral, groq, claude, ollama, gemini, openrouter, tools
from gepetto import response as gepetto_response
from gepetto import weather, sentry, summary, replicate, images
from config import Config
from gepetto.helpers.discord_utils import extract_recipe_from_webpage, get_weather_forecast, summarise_webpage_content, create_image

logger = logging.getLogger('discord')

def register_message_handler(bot, chatbot, state):
    @bot.event
    async def on_message(message):
        message_guard = guard.BotGuard()
        message_blocked, abusive_reply = message_guard.should_block(message, bot, Config.DISCORD_SERVER_ID, chatbot)
        if message_blocked:
            if abusive_reply:
                logger.info("Blocked message from: " + message.author.name + " and abusing them")
                await message.channel.send(f"{random.choice(abusive_responses)}.")
            return

        question = message.content.split(' ', 1)[1][:500].replace('\r', ' ').replace('\n', ' ')
        logger.info(f'Question: {question}')
        if not any(char.isalpha() for char in question):
            await message.channel.send(f'{message.author.mention} {random.choice(abusive_responses)}.')
            return

        if "--strict" in question.lower():
            question = question.lower().replace("--strict", "")
            temperature = 0.1
        elif "--wild" in question.lower():
            question = question.lower().replace("--wild", "")
            temperature = 1.5
        elif "--tripping" in question.lower():
            question = question.lower().replace("--tripping", "")
            temperature = 1.9
        else:
            temperature = 1.0

        pattern = r"👀\s*\<?(http|https):"

        try:
            lq = question.lower().strip()
            async with message.channel.typing():
                if "--no-logs" in question.lower():
                    context = []
                    question = question.lower().replace("--no-logs", "")
                else:
                    if chatbot.uses_logs:
                        context = await get_history_as_openai_messages(message.channel, bot)
                    else:
                        context = []
                if '--serious' in question.lower():
                    question = question.lower().replace("--serious", "")
                    system_prompt = "You should respond in a very serious, professional and formal manner.  The user is a professional and simply wants a clear answer to their question."
                else:
                    system_prompt = None
                if message.author.bot:
                    question = question + ". Please be very concise, curt and to the point.  The user in this case is a discord bot."
                if question.lower().startswith("!image"):
                    await message.channel.send("Image generation is now handled by the scheduled task.")
                    return
                if '--o1' in question.lower():
                    question = question.lower().replace("--o1", "")
                    override_model = gpt.Model.GPT_O1_MINI.value[0]
                else:
                    override_model = None
                optional_args = {}
                if override_model is not None:
                    optional_args['model'] = override_model
                if '--reasoning' in question.lower():
                    await message.reply(f'{message.author.mention} **Reasoning:** {state.previous_image_reasoning}\n**Themes:** {state.previous_image_themes}\n**Image Prompt:** {state.previous_image_prompt}', mention_author=True)
                    return
                if '--thinking' in question.lower():
                    await message.reply(f'{message.author.mention} **Thinking:** {state.previous_reasoning_content}', mention_author=True)
                    return
                messages = build_messages(question, context, system_prompt=system_prompt)
                response = await chatbot.chat(messages, temperature=temperature, tools=tools.tool_list, **optional_args)
                if response.reasoning_content:
                    state.previous_reasoning_content = truncate(response.reasoning_content, 1800, '[... Truncated ...]')
                if response.tool_calls:
                    tool_call = response.tool_calls[0]
                    arguments = json.loads(tool_call.function.arguments)
                    fname = tool_call.function.name
                    if fname == 'extract_recipe_from_webpage':
                        recipe_url = arguments.get('url', '')
                        if ('example.com' in recipe_url) or ('http' not in question.lower()):
                            original_usage = response.usage
                            response = await chatbot.chat(messages, temperature=temperature, tools=[], **optional_args)
                            response = response.message.strip()[:1800] + "\n" + response.usage + "\n" + original_usage
                            await message.reply(f'{message.author.mention} {response}')
                        else:
                            await extract_recipe_from_webpage(message, arguments.get('prompt', ''), arguments.get('url', ''), chatbot)
                    elif fname == 'get_weather_forecast':
                        await get_weather_forecast(message, arguments.get('prompt', ''), arguments.get('locations', []), chatbot)
                    elif fname == 'summarise_webpage_content':
                        await summarise_webpage_content(message, arguments.get('prompt', ''), arguments.get('url', ''), chatbot)
                    elif fname == 'create_image':
                        await create_image(message, arguments.get('prompt', ''), model="nvidia/sana:88312dcb9eaa543d7f8721e092053e8bb901a45a5d3c63c84e0a5aa7c247df33")
                    else:
                        logger.info(f'Unknown tool call: {fname}')
                        await message.reply(f'{message.author.mention} I am a silly sausage and don\'t know how to do that.', mention_author=True)
                    return
                else:
                    response_text = response.message
                    response_text = re.sub(r'\[tokens used.+Estimated cost.+]', '', response_text, flags=re.MULTILINE)
                    response_text = re.sub(r"Gepetto' said: ", '', response_text, flags=re.MULTILINE)
                    response_text = re.sub(r"Minxie' said: ", '', response_text, flags=re.MULTILINE)
                    response_text = re.sub(r"^.*At \\d{4}-\\d{2}.+said?", "", response_text, flags=re.MULTILINE)
                    logger.info(response.usage)
                    response = truncate(response_text.strip(), 1900, '[... Truncated ...]') + "\n" + response.usage_short
                await message.reply(f'{message.author.mention} {response}')
        except Exception as e:
            logger.error(f'Error generating response: {e}')
            await message.reply(f'{message.author.mention} I tried, but my attempt was as doomed as Liz Truss.  Please try again later.', mention_author=True)
