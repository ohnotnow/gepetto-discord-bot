# Discord OpenAI Bot

This bot uses OpenAI to generate responses to messages in a Discord server. It listens for mentions of the bot and generates responses using OpenAI's GPT chat model. It has some special functionality to track the number of times a user has mentioned the bot recently and limit the number of OpenAI calls.

It has a couple of extra options to do common things.  Eg:
```
@Gepetto create an image of a rocket flying through space
@Gepetto summarise https://www.example.com/an/article
@Gepetto summarise <https://www.youtube.com/watch?v=123f830q9>
```
The youtube one depends on their being subtitles/transcripts attached to the video.  The summarise command is a little limited (currently hard-coded) in scope due to token limits on the text you can send to the cheaper OpenAI models.

## Environment Variables

The following environment variables are required:

- `DISCORD_BOT_TOKEN`: Your Discord bot token
- `DISCORD_SERVER_ID`: The ID of your Discord server
- `OPENAI_API_KEY`: Your OpenAI API key
- `DEFAULT_MODEL_ENGINE`: The engine of the OpenAI model to use (default is 'gpt-3.5-turbo')

## Running the Script

To run the bot:

1. Install the required Python dependencies: `discord.py` and `openai`.  You can install these by running `pip install -r requirements.txt`.
2. Set your environment variables. These can be set in your shell, or stored in a `.env` file at the root of your project.
3. Run `python main.py` in the root of your project to start the bot.

## Docker Deployment

A `Dockerfile` is included in this repository. This allows you to easily build and run your bot inside a Docker container.  Please see the `run.sh` script for an example of building and running the container.
