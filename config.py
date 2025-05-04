import os

class Config:
    DISCORD_SERVER_ID = os.getenv("DISCORD_SERVER_ID", "not_set")
    OPENAI_MODEL_ENGINE = os.getenv("OPENAI_MODEL_ENGINE", "gpt-4.1-mini")
    BOT_LOCATION = os.getenv('BOT_LOCATION', 'dunno')
    CHAT_IMAGE_HOUR = int(os.getenv('CHAT_IMAGE_HOUR', 17))
    FEATURE_RANDOM_CHAT = os.getenv("FEATURE_RANDOM_CHAT", "False").lower() in ("true", "1", "yes")
    FEATURE_HORROR_CHAT = os.getenv("FEATURE_HORROR_CHAT", "False").lower() in ("true", "1", "yes")
    DISCORD_BOT_CHANNEL_ID = os.getenv('DISCORD_BOT_CHANNEL_ID', 'Invalid').strip()
    DISCORD_BOT_DEFAULT_PROMPT = os.getenv('DISCORD_BOT_DEFAULT_PROMPT', None)
    DISCORD_BOT_ALTERNATE_PROMPT = os.getenv('DISCORD_BOT_ALTERNATE_PROMPT', None)
    DISCORD_BOT_MODEL = os.getenv("DISCORD_BOT_MODEL", None)
    BOT_NAME = os.getenv("BOT_NAME", None)
    BOT_PROVIDER = os.getenv("BOT_PROVIDER", "openai")
    CHAT_IMAGE_ENABLED = os.getenv("CHAT_IMAGE_ENABLED", "False").lower() in ("true", "1", "yes")
    IMAGE_MODEL = os.getenv("IMAGE_MODEL", "bytedance/sdxl-lightning-4step:5599ed30703defd1d160a25a63321b4dec97101d98b4674bcc56e41f62f35637")
    DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", 'not_set')
