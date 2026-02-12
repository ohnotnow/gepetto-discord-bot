# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

A Discord bot that uses LLMs (via LiteLLM) to chat, generate images, summarise content, and run scheduled tasks. Named "Gepetto" by default.

## Tech Stack

- **Python 3.11+** with **uv** for dependency management
- **discord.py** for Discord integration
- **LiteLLM** for multi-provider LLM support (OpenAI, Anthropic, OpenRouter, Groq, Perplexity)
- **Replicate** for image generation (Flux, etc.)
- **Docker** for deployment

## Commands

```bash
uv sync                                      # Install dependencies
uv run python main.py                        # Run the bot
uv run pytest                                # Run all tests (56 tests)
uv run pytest tests/test_helpers.py          # Run single test file
uv run pytest tests/test_helpers.py::test_function_name -v  # Run single test
```

## Architecture

### LLM Providers (`src/providers/`)
All providers inherit from `BaseModel` in `base.py` which wraps LiteLLM:
```python
from src.providers import gpt, claude
chatbot = gpt.Model()  # or claude.Model()
response = await chatbot.chat(messages)
```
The model string format is `{provider}/{model}` (e.g., "openai/gpt-4o-mini"). You can pass a full LiteLLM model string directly to `chat()`.

### Image Generation (`src/media/`)
Uses factory pattern in `replicate.py`:
```python
from src.media import replicate
model = replicate.get_image_model()  # Random from enabled models
image_url = await model.generate("a cat in space")
```

### Tool Dispatch (`src/tools/`)
Simple tools use `ToolDispatcher` in `handlers.py`. Complex tools (that need LLM continuation) remain inline in `main.py`. Tool definitions are in `definitions.py`.

### Bot State
Global state is encapsulated in `BotState` dataclass in `main.py` - tracks previous image info, horror history, daily counts.

### Scheduled Tasks (in main.py)
- `make_chat_image()` - Daily image based on chat history
- `make_chat_video()` - Video generation (similar pattern)
- `horror_chat()` - Random horror stories overnight
- `random_chat()` - Random interjections (disabled by default)
- `check_birthdays()` - Birthday announcements

## Key Environment Variables

- `DISCORD_BOT_TOKEN`, `DISCORD_SERVER_ID`, `DISCORD_BOT_CHANNEL_ID` - Discord config
- `BOT_PROVIDER`, `BOT_MODEL` - LLM selection (e.g., "openai", "gpt-4o")
- `REPLICATE_API_KEY` - For image generation
- `USER_LOCATIONS` - Location hints for image generation (10% chance to apply)
- `CAT_DESCRIPTIONS` - Cat descriptions for image generation (always applies when set)
- `CHAT_IMAGE_ENABLED`, `CHAT_IMAGE_HOUR` - Daily image feature

See README.md for full environment variable list.

## Design Decisions

1. **"Random random" in image styles** - `get_extra_guidelines()` in `images.py` intentionally uses cascading random calls for variety, not a single roll.

2. **Broad exception handling** - Some try/except blocks are intentionally broad due to varied LLM response formats.

3. **Config as code for Replicate** - Model configs in `replicate.py` use a dict pattern rather than if/elif chains.
