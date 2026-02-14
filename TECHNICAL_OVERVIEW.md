# Technical Overview

Last updated: 2026-01-31

## What This Is

A Discord bot ("Gepetto") that uses LLMs via LiteLLM to chat, generate images, summarise content, and run scheduled creative tasks.

## Stack

- **Python 3.11+** with `uv` for dependency management
- **discord.py** 2.3.0+ - Discord integration
- **LiteLLM** 1.66.3+ - Multi-provider LLM abstraction
- **Replicate** 0.32.1+ - Image generation (Flux, Sora, etc.)
- **trafilatura** - Web content extraction
- **youtube_transcript_api** - YouTube transcript fetching
- **PyPDF2** - PDF text extraction

## Directory Structure

```
src/
├── platforms/       # Platform abstraction layer (Discord, future Matrix)
│   ├── __init__.py  # Factory: get_platform() based on BOT_BACKEND
│   ├── base.py      # ChatMessage dataclass, Channel/Platform protocols
│   └── discord_adapter.py  # Discord implementation wrapping discord.py
├── providers/       # LLM provider wrappers (all inherit from BaseModel)
│   ├── base.py      # BaseModel with LiteLLM integration
│   ├── gpt.py       # OpenAI (minimal, just sets flag)
│   ├── claude.py    # Anthropic
│   ├── grok.py      # Grok (Twitter/X search via x_search)
│   ├── groq.py      # Groq
│   ├── openrouter.py
│   ├── perplexity.py  # Web search
│   └── response.py  # ChatResponse/FunctionResponse dataclasses
├── media/           # Media generation
│   ├── replicate.py # Image model factory + configs
│   ├── sora.py      # Video generation
│   └── images.py    # Chat-to-image prompt building
├── content/         # Content extraction/summarization
│   ├── summary.py   # URL→text (YouTube, PDF, web)
│   ├── weather.py   # Weather forecasts
│   └── sentry.py    # Sentry issue parsing
├── tools/           # Tool calling infrastructure
│   ├── definitions.py  # Tool schemas (OpenAI format)
│   ├── handlers.py     # ToolDispatcher class
│   └── calculator.py   # Math expression evaluator
├── tasks/           # Scheduled task helpers
│   └── birthdays.py
├── utils/           # Shared utilities
│   ├── constants.py # Tunable parameters
│   ├── helpers.py   # Date formatting, media download, text cleaning
│   └── guard.py     # BotGuard rate limiting
├── embeddings/      # Text embeddings for semantic search
│   ├── base.py      # BaseEmbeddings + cosine_similarity()
│   ├── response.py  # EmbeddingsResponse dataclass
│   ├── openai.py    # OpenAI embeddings provider
│   └── openrouter.py # OpenRouter embeddings provider
└── persistence/     # State persistence (SQLite + JSON)
    ├── json_store.py    # Legacy JSON file storage
    ├── image_store.py   # SQLite image history (themes, prompts)
    ├── memory_store.py  # SQLite user memories and bios
    ├── url_store.py     # SQLite URL history and summaries
    └── activity_store.py # SQLite user activity tracking

main.py              # Entry point, bot setup, event handlers, scheduled tasks
tests/               # pytest-based tests
```

## Architecture

### Platform Layer

The bot runs on a platform abstraction that decouples business logic from Discord-specific code. Set `BOT_BACKEND` to choose the platform (currently only `discord`; `matrix` planned).

- **ChatMessage** - Platform-agnostic message dataclass. Contains author info, content, channel/server IDs, and a `raw` escape hatch for the original platform message.
- **Channel** - Protocol for channel operations: send, send_file, history, typing, permissions.
- **Platform** - Protocol for bot lifecycle: event registration, scheduling, channel access, running.

Only `src/platforms/discord_adapter.py` imports discord.py. All other code works with the protocol types.

### LLM Provider System

All providers inherit from `BaseModel` which wraps LiteLLM:

```
BaseModel (base.py)
├── GPTModel (gpt.py)         # OpenAI - uses_logs=True
├── ClaudeModel (claude.py)   # Anthropic
├── GroqModel (groq.py)       # Groq
├── OpenrouterModel           # OpenRouter
└── PerplexityModel           # Perplexity (web search)
```

Model string format: `{provider}/{model}` (e.g., "openai/gpt-4o-mini")

### Image Generation

Factory pattern in `replicate.py`:
- `get_image_model(name)` returns `ImageModel` instance
- `MODEL_CONFIGS` dict maps model prefixes to (default_model, cost, params, in_pool)
- Random model selection from models with `in_pool=True`

### Tool Dispatch

Simple tools → `ToolDispatcher` in `handlers.py`:
```
calculate, get_weather_forecast, get_sentry_issue_summary,
summarise_webpage_content, web_search, search_url_history (conditional)
```

Complex tools (needing LLM continuation) → inline in `main.py`:
```
create_image, extract_recipe_from_webpage
```

### Bot State

```python
@dataclass
class BotState:
    previous_image_description: str
    previous_image_reasoning: str
    previous_image_prompt: str
    previous_image_themes: str
    previous_reasoning_content: str
    horror_history: list
    daily_image_count: int
```

### Rate Limiting

`BotGuard` in `guard.py`:
- Tracks mention counts per user
- Blocks: DMs, other servers, bots, empty messages, rate-limited users
- Returns (blocked: bool, abusive_reply: bool)

### Persistence Layer

SQLite-based storage in `./data/gepetto.db`:

**ImageStore** - Tracks image generation history per server:
- Stores themes, reasoning, prompts, URLs
- Used to avoid repeating themes in daily images
- Auto-prunes to `MAX_ENTRIES_PER_SERVER` (10)

**MemoryStore** - User memories and bios per server:
- `Memory` - Short facts with optional expiry (e.g., "Alice is on holiday until Friday")
- `UserBio` - Long-term profile summaries
- `get_context_for_user()` returns formatted context for prompts
- Privacy controls via `delete_user_data()`

**UrlStore** - URL history and summaries per server:
- Stores URLs, summaries, keywords, poster info
- `search()` finds URLs matching query terms (case-insensitive)
- `url_exists()` checks for duplicates before saving
- Auto-prunes to `MAX_ENTRIES_PER_SERVER` (500)

**ActivityStore** - User activity tracking per server:
- Tracks when each user last sent a message
- `record_activity()` upserts user's last activity timestamp
- `get_last_activity()` returns when user was last seen
- Used by the "catch me up" feature

### User Memory System

When `ENABLE_USER_MEMORY=true`:
- Memories are included in prompts (30% chance per eligible memory, max 3)
- Users can say "delete my info" / "forget me" to remove their data

When `ENABLE_USER_MEMORY_EXTRACTION=true`:
- Scheduled task extracts memories from chat history daily
- LLM identifies facts about users and categorises them
- Only one bot instance should run extraction (others just read)

### Embeddings

Setting `EMBEDDING_PROVIDER` enables the embeddings infrastructure:
- Supports "openai" or "openrouter" providers
- Uses `src/embeddings` module for vector generation
- Embeddings stored as JSON in SQLite (no vector database needed)

### URL History System

URL history uses semantic search. Requires `EMBEDDING_PROVIDER` to be configured.

When `ENABLE_URL_HISTORY=true`:
- Bot has access to `search_url_history` tool
- Users can ask "what was that link about X?" to search past URLs
- Uses vector embeddings for semantic search (e.g., "that auth thing" finds OAuth articles)
- Results filtered by similarity threshold (0.5) to ensure quality matches

When `ENABLE_URL_HISTORY_EXTRACTION=true`:
- Scheduled task scans `URL_HISTORY_CHANNELS` daily for new URLs
- Extracts content using existing `summary.get_text()` function
- LLM generates short summary and keywords for each URL
- Generates embedding for each summary
- Only one bot instance should run extraction (others just search)

### Catch-Up System

When `ENABLE_CATCH_UP=true`:
- Bot has access to the `catch_up` tool and can respond to catch-up requests

When `ENABLE_CATCH_UP_TRACKING=true`:
- Tracks user activity in channels listed in `URL_HISTORY_CHANNELS`
- Activity recorded passively on every non-bot message (before bot mention check)
- Only one bot instance should enable this (others just respond to requests)
- LLM tool `catch_up` triggered naturally by phrases like "catch me up", "what did I miss", "fill me in", "what's been going on", etc.
- Fetches messages from monitored channels since user's last activity
- Capped at 48 hours lookback, 500 messages per channel
- LLM generates a personality-infused summary of missed content

## Key Features

| Feature | Trigger | Handler |
|---------|---------|---------|
| Chat | @mention with text | `on_message` |
| Image generation | LLM tool call `create_image` | `create_image()` |
| Web search | LLM tool call `web_search` | `perplexity.search()` |
| URL summarization | 👀 emoji + URL | `summarise_webpage_content()` |
| Weather | "weather" in prompt | `get_weather_forecast()` |
| Calculator | Math expressions | `calculator.calculate()` |
| Spell check | "spell" in prompt | Routes to Marvin persona (cheap model) |
| Privacy | "delete my info" / "forget me" | `memory_store.delete_user_data()` |
| URL history search | LLM tool call `search_url_history` | `url_store.search()` |
| Catch me up | LLM tool call `catch_up` | `handle_catch_up()` |
| Twitter search | LLM tool call `twitter_search` | `grok.search()` |

## Scheduled Tasks

| Task | Schedule | Description |
|------|----------|-------------|
| `make_chat_image` | Daily at `CHAT_IMAGE_HOUR` | Generates image from chat history |
| `make_chat_video` | Daily at `CHAT_IMAGE_HOUR + 15min` | Generates video from chat |
| `horror_chat` | Hourly (night only) | Posts creepy one-liners |
| `random_chat` | Hourly | Random interjections (disabled by default) |
| `say_happy_birthday` | 11 AM UK | Birthday announcements |
| `reset_daily_image_count` | 3 AM UK | Resets daily image limit |
| `extract_user_memories` | Daily at `MEMORY_EXTRACTION_HOUR` | Extracts user facts from chat |
| `extract_url_history` | Daily at `URL_HISTORY_EXTRACTION_HOUR` | Scans channels for URLs, summarises and stores them |

## Constants (utils/constants.py)

| Constant | Value | Purpose |
|----------|-------|---------|
| `MAX_DAILY_IMAGES` | 10 | User image generation limit |
| `HISTORY_HOURS` | 8 | Chat history window |
| `HISTORY_MAX_MESSAGES` | 200 | Max messages in context |
| `HORROR_CHAT_COOLDOWN_HOURS` | 8 | Min time between horror posts |
| `LIZ_TRUSS_PROBABILITY` | 0.05 | Random Liz Truss mention chance |
| `MEMORY_COOLDOWN_HOURS` | 24 | Don't reference same memory within this period |
| `MEMORY_INCLUSION_PROBABILITY` | 0.3 | Chance to include eligible memory |
| `MEMORY_MAX_PER_PROMPT` | 3 | Max memories per prompt |
| `CATCH_UP_MAX_HOURS` | 48 | Maximum lookback window for catch-up |
| `CATCH_UP_MAX_MESSAGES` | 500 | Max messages to fetch per channel |

## Testing

- **Framework**: pytest with pytest-asyncio
- **Pattern**: Unit tests in `tests/` directory
- **Run**: `uv run pytest`

## Local Development

```bash
uv sync                    # Install dependencies
uv run python main.py      # Run the bot
uv run pytest              # Run tests
```

## Key Environment Variables

| Variable | Required | Purpose |
|----------|----------|---------|
| `BOT_BACKEND` | No | Platform backend: "discord" (default) or "matrix" (future) |
| `DISCORD_BOT_TOKEN` | Yes | Discord authentication |
| `DISCORD_SERVER_ID` | Yes | Server to operate in |
| `DISCORD_BOT_CHANNEL_ID` | Yes | Channel for scheduled tasks |
| `BOT_PROVIDER` | Yes | LLM provider (openai, anthropic, groq, openrouter) |
| `BOT_MODEL` | Yes | Default model name |
| `REPLICATE_API_KEY` | For images | Replicate API access |
| `CHAT_IMAGE_ENABLED` | No | Enable daily image feature |
| `FEATURE_HORROR_CHAT` | No | Enable horror posts |
| `ENABLE_USER_MEMORY` | No | Enable reading user memories |
| `ENABLE_USER_MEMORY_EXTRACTION` | No | Enable memory extraction task |
| `MEMORY_EXTRACTION_HOUR` | No | Hour for extraction (default: 3) |
| `EMBEDDING_PROVIDER` | No | Enables embeddings: "openai" or "openrouter" |
| `EMBEDDING_MODEL` | No | Model name (default: text-embedding-3-small) |
| `ENABLE_URL_HISTORY` | No | Enable URL history search (requires EMBEDDING_PROVIDER) |
| `ENABLE_URL_HISTORY_EXTRACTION` | No | Enable URL extraction task (requires EMBEDDING_PROVIDER) |
| `URL_HISTORY_CHANNELS` | No | Comma-separated channel IDs to scan |
| `URL_HISTORY_EXTRACTION_HOUR` | No | Hour for URL extraction (default: 4) |
| `EMBEDDING_PROVIDER` | No | Embeddings API: "openai" or "openrouter" |
| `EMBEDDING_MODEL` | No | Model name (default: text-embedding-3-small) |
| `ENABLE_CATCH_UP` | No | Enable catch-up tool for responding to requests |
| `ENABLE_CATCH_UP_TRACKING` | No | Enable activity tracking (only one bot instance) |
| `ENABLE_TWITTER_SEARCH` | No | Enable Twitter/X search via Grok (requires OPENROUTER_API_KEY) |
| `SPELLCHECK_MODEL` | No | Model for spell check (e.g., "groq/llama-3.1-8b-instant") |

## Design Notes

1. **"Random random" in image styles** - `get_extra_guidelines()` uses cascading random calls intentionally for maximum variety
2. **Broad exception handling** - Some try/except blocks are intentionally broad due to varied LLM response formats
3. **Theme persistence** - Previous image themes stored in SQLite (`ImageStore`) to avoid repetition
4. **NSFW filtering** - Text cleaned before image prompts via `remove_nsfw_words()`
5. **Liz Truss** - 5% chance of random Liz Truss references (it's a British thing)
6. **Multi-bot memory setup** - Use `ENABLE_USER_MEMORY=true` on all bots, `ENABLE_USER_MEMORY_EXTRACTION=true` on only one
7. **Marvin spellcheck** - Routes spell check requests to a cheaper model with a depressed robot persona
