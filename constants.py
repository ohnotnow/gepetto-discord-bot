"""
Constants used throughout the Gepetto Discord bot.
"""

# History and message limits
HISTORY_HOURS = 8
HISTORY_MESSAGE_LIMIT = 1000
HISTORY_MAX_MESSAGES = 200
MAX_WORDS_TRUNCATION = 12000

# Discord limits
DISCORD_MESSAGE_LIMIT = 1800

# Image generation
MAX_DAILY_IMAGES = 10
MAX_HORROR_HISTORY = 40

# Random chat thresholds
RANDOM_CHAT_PROBABILITY = 0.3
HORROR_CHAT_PROBABILITY = 0.1
HORROR_CHAT_COOLDOWN_HOURS = 8
LIZ_TRUSS_PROBABILITY = 0.05
ALTERNATE_PROMPT_PROBABILITY = 0.1

# Minimum messages required
MIN_MESSAGES_FOR_RANDOM_CHAT = 5
MIN_MESSAGES_FOR_CHAT_IMAGE = 2

# Time ranges (hours in 24h format)
NIGHT_START_HOUR = 23
NIGHT_END_HOUR = 7
DAY_START_HOUR = 7
DAY_END_HOUR = 19

# UK holidays that affect chat image generation (month-day format)
UK_HOLIDAYS = [
    "December 25",
    "December 26",
    "December 27",
    "December 28",
    "January 1",
    "January 2",
]

# Playful insult responses for rate-limited or invalid requests
ABUSIVE_RESPONSES = [
    "Wanker",
    "Asshole",
    "Prick",
    "Twat",
    "Asshat",
    "Knob",
    "Dick",
    "Tosser",
    "Cow",
    "Cockwomble",
    "Anorak",
    "Knickers",
    "Fanny",
    "Sigh",
    "Big girl's blouse",
]
