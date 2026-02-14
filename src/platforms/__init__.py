import os


def get_platform():
    backend = os.getenv("BOT_BACKEND", "discord")
    if backend == "discord":
        from .discord_adapter import DiscordPlatform
        return DiscordPlatform()
    elif backend == "matrix":
        raise NotImplementedError("Matrix support coming soon")
    else:
        raise ValueError(f"Unknown BOT_BACKEND: {backend}")
