# Gepetto Discord Bot - Project Overview

## What This Is

A Discord bot that uses LLMs (via LiteLLM) to chat, generate images, summarise content, and run scheduled tasks. Named "Gepetto" by default.

## Tech Stack

- **Python 3.11+** with **uv** for dependency management
- **discord.py** for Discord integration
- **LiteLLM** for multi-provider LLM support (OpenAI, Anthropic, OpenRouter, Groq, Perplexity)
- **Replicate** for image generation (Flux, etc.)
- **Docker** for deployment

## Running the Project

```bash
uv sync                    # Install dependencies
uv run python main.py      # Run the bot
uv run pytest              # Run tests (56 tests)
```

## Directory Structure

```
gepetto_discord_bot/
├── main.py                 # Entry point, Discord event handlers, scheduled tasks
├── pyproject.toml          # Dependencies (uv)
├── src/
│   ├── providers/          # LLM providers (all use LiteLLM BaseModel)
│   │   ├── base.py         # BaseModel class - foundation for all providers
│   │   ├── response.py     # ChatResponse, FunctionResponse, split_for_discord()
│   │   ├── gpt.py, claude.py, groq.py, openrouter.py, perplexity.py
│   ├── tools/              # Function calling / tool use
│   │   ├── definitions.py  # tool_list - available tools for LLMs
│   │   ├── handlers.py     # ToolDispatcher for simple tool handlers
│   │   └── calculator.py
│   ├── media/              # Image/video generation
│   │   ├── images.py       # Chat image prompt generation
│   │   ├── replicate.py    # ImageModel factory + Replicate API
│   │   └── sora.py         # Video generation
│   ├── content/            # Content processing
│   │   ├── summary.py      # Webpage summarisation
│   │   ├── websearch.py    # Web search
│   │   ├── weather.py      # Met Office weather
│   │   └── sentry.py       # Sentry issue analysis
│   ├── persistence/        # Data storage
│   │   ├── memory.py       # Per-user memory (user_data/*.json)
│   │   ├── json_store.py   # Unified JSON persistence
│   │   └── random_facts.py
│   ├── tasks/
│   │   └── birthdays.py
│   └── utils/
│       ├── constants.py    # Magic numbers, UK holidays, etc.
│       ├── helpers.py      # Date formatting, media helpers, text processing
│       └── guard.py        # Rate limiting
└── tests/                  # pytest tests
```

## Key Patterns

### LLM Providers
All providers inherit from `BaseModel` in `src/providers/base.py` which wraps LiteLLM. Use like:
```python
from src.providers import gpt, claude
chatbot = gpt.Model()  # or claude.Model()
response = await chatbot.chat(messages)
```

### Image Generation
Uses factory pattern in `src/media/replicate.py`:
```python
from src.media import replicate
model = replicate.get_image_model()  # Random from enabled models
image_url = await model.generate("a cat in space")
```

### Tool Dispatch
Simple tools use `ToolDispatcher` in `src/tools/handlers.py`. Complex tools (that need LLM continuation) remain inline in `main.py`.

### Bot State
Global state is encapsulated in `BotState` dataclass in `main.py` - tracks previous image info, horror history, daily counts.

## Environment Variables

Key ones (see README for full list):
- `DISCORD_BOT_TOKEN`, `DISCORD_SERVER_ID`, `DISCORD_BOT_CHANNEL_ID` - Discord config
- `BOT_PROVIDER`, `BOT_MODEL` - LLM selection (e.g., "openai", "gpt-4o")
- `REPLICATE_API_KEY` - For image generation
- `USER_LOCATIONS` - Location hints for image generation (10% chance to apply)
- `CAT_DESCRIPTIONS` - Cat descriptions for image generation (always applies when set)
- `CHAT_IMAGE_ENABLED`, `CHAT_IMAGE_HOUR` - Daily image feature

## Scheduled Tasks (in main.py)

- `make_chat_image()` - Daily image based on chat history
- `make_chat_video()` - Video generation (similar pattern)
- `horror_chat()` - Random horror stories overnight
- `random_chat()` - Random interjections (disabled by default)
- `check_birthdays()` - Birthday announcements

## Design Decisions

1. **"Random random" in image styles** - `get_extra_guidelines()` in `images.py` intentionally uses cascading random calls for variety, not a single roll.

2. **Broad exception handling** - Some try/except blocks are intentionally broad due to varied LLM response formats.

3. **Hardcoded image model** - `create_image()` hardcodes the model to "best affordable option" rather than using the parameter.

4. **Config as code for Replicate** - Model configs in `replicate.py` use a dict pattern rather than if/elif chains.

## Testing

```bash
uv run pytest                    # All tests
uv run pytest tests/test_helpers.py  # Specific file
```

Tests cover: helpers, calculator, persistence, tool dispatcher. Integration tests with mocked Discord/LLM are future work.
