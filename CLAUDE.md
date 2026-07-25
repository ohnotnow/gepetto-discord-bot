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
uv run pytest                                # Run all tests (568 tests)
uv run pytest tests/test_helpers.py          # Run single test file
uv run pytest tests/test_helpers.py::test_function_name -v  # Run single test

# Iterate on the corpse image-prompt pipeline without waiting for the daily cron:
uv run python scripts/try_chat_image.py samples/sample_chat.txt           # dry-run, free
uv run python scripts/try_chat_image.py samples/sample_chat.txt --image   # actually generate

# Inspect what the Met Office actually returns and what reaches the LLM:
uv run python scripts/try_weather.py Glasgow --hourly                     # free
uv run python scripts/try_weather.py Glasgow --hourly --llm               # + the friendly forecast
```

## Architecture

### Platform Layer (`src/platforms/`)
The bot uses a platform abstraction layer. `BOT_BACKEND` env var selects the platform (default: `discord`). All business logic uses `ChatMessage`, `Channel`, and `Platform` protocols — `import discord` should only appear in `src/platforms/discord_adapter.py` and test files.

### LLM Providers (`src/providers/`)
All providers inherit from `BaseModel` in `base.py` which wraps LiteLLM:
```python
from src.providers import gpt, claude
chatbot = gpt.Model()  # or claude.Model()
response = await chatbot.chat(messages)
```
The model string format is `{provider}/{model}` (e.g., "openai/gpt-4o-mini"). You can pass a full LiteLLM model string directly to `chat()`.

### Image Generation (`src/media/`)
> **Before changing anything here:** run `ant show gepettodiscordbot-AkRXV` for the full flow notes — `create_image` vs `make_chat_image`, the corpse pipeline, and which traps to avoid. This is the most-tinkered-with part of the bot; the note will save you re-deriving it.

`IMAGE_PROVIDER` env var selects between `"replicate"` (default), `"fal"`, and `"openai"` (gpt-image-2 via the dedicated images.generate endpoint). All three expose the same `ImageModel` interface via a routing function:
```python
from src.media import get_image_model
model = get_image_model()  # Random from enabled models on the active provider
image_url = await model.generate("a cat in space")
```
Each provider (`replicate.py`, `fal.py`) has its own `MODEL_CONFIGS` with provider-specific model names and parameters. FAL is lazily imported only when selected.

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

- `BOT_BACKEND` - Platform selection (default: "discord")
- `DISCORD_BOT_TOKEN`, `DISCORD_SERVER_ID`, `DISCORD_BOT_CHANNEL_ID` - Discord config
- `BOT_PROVIDER`, `BOT_MODEL` - LLM selection (e.g., "openai", "gpt-4o")
- `REPLICATE_API_KEY` - For image generation
- `USER_LOCATIONS` - Location hints for image generation (10% chance to apply)
- `CAT_DESCRIPTIONS` - Cat descriptions for image generation (always applies when set)
- `CHAT_IMAGE_ENABLED`, `CHAT_IMAGE_HOUR` - Daily image feature

See README.md for full environment variable list.

## Design Decisions

1. **Style variety is a curated catalogue, not an LLM pick** - the daily image's style comes from `random.choice` over `src/media/style_catalogue.py` with a globally shared anti-repetition history. Do not reintroduce LLM style-picking or bolt-on random style nudges: the LLM's style prior collapses to ~50 favourites, and extra nudges appended after the corpse assembler fight the style it committed to (both were removed 2026-07-19 — see ant gepettodiscordbot-AkRXV).

2. **Weather forecasts use bucketed hourly data, not the daily endpoint** - `build_met_office_forecast()` in `src/content/weather.py` calls `/point/hourly` for today and tomorrow and summarises it into named local-time periods (Overnight/Morning/Afternoon/Evening), falling back to `/point/daily` only beyond the hourly feed's ~48-hour reach. Do not "simplify" this back to a single daily call: the daily endpoint collapses a day into day/night averages, so it cannot say "wet morning, bright afternoon" and the LLM invents the timing instead — forecasts read as plausible but wrong (fixed 2026-07-25 — see ant gepettodiscordbot-C8ggs for the traps, especially why tonight's rain needs its own tail section). Run `uv run python scripts/try_weather.py Glasgow --hourly` before changing anything here.

3. **Broad exception handling** - Some try/except blocks are intentionally broad due to varied LLM response formats.

4. **Config as code for Replicate** - Model configs in `replicate.py` use a dict pattern rather than if/elif chains.
