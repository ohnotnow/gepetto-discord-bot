#!/usr/bin/env python3
"""Dev tool for fast iteration on the corpse image-prompt pipeline.

Reads a chat log from disk, runs it through `image_prompt_corpse.build()`
exactly as the daily scheduled job does, prints each stage as it happens,
and optionally calls the image generator at the end.

Examples:
    uv run python scripts/try_chat_image.py samples/sample_chat.txt
    uv run python scripts/try_chat_image.py samples/sample_chat.txt --image
    uv run python scripts/try_chat_image.py samples/sample_chat.txt --image -v

Env loading:
    The script reads `.env` from the project root if present (KEY=value
    lines, # comments and blank lines ignored). Existing shell env wins.

Outputs:
    A timestamped directory under ./samples/output/ is created per run.
    Always written: run.log (full discord-logger transcript), prompt.md
    (assembled prompt + themes + reasoning).
    When --image is passed: image.png (the generated image).
"""

import argparse
import asyncio
import logging
import os
import shutil
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def _load_dotenv_if_present() -> None:
    env_path = PROJECT_ROOT / ".env"
    if not env_path.is_file():
        return
    for raw in env_path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        os.environ.setdefault(key, value)


def _setup_logging(output_dir: Path, verbose: bool) -> logging.Handler:
    """Wire the 'discord' logger up to stderr + a per-run log file."""
    log_level = logging.DEBUG if verbose else logging.INFO
    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)-7s %(name)s %(message)s",
        datefmt="%H:%M:%S",
    )

    stream_handler = logging.StreamHandler(sys.stderr)
    stream_handler.setFormatter(formatter)

    file_handler = logging.FileHandler(output_dir / "run.log", mode="w")
    file_handler.setFormatter(formatter)

    discord_logger = logging.getLogger("discord")
    discord_logger.setLevel(log_level)
    discord_logger.addHandler(stream_handler)
    discord_logger.addHandler(file_handler)
    discord_logger.propagate = False

    # Quiet third-party noise.
    logging.getLogger("LiteLLM").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    return file_handler


def _get_chatbot():
    """Mirror main.get_chatbot() without dragging in the rest of main.py."""
    from src.providers import claude, gpt, groq, openrouter

    provider = os.getenv("BOT_PROVIDER", "openai")
    if provider == "groq":
        return groq.GroqModel()
    if provider == "anthropic":
        return claude.ClaudeModel()
    if provider == "openrouter":
        return openrouter.OpenrouterModel()
    return gpt.GPTModel()


def _save_image(image_url_or_path: str, dest: Path) -> None:
    if image_url_or_path.startswith(("http://", "https://")):
        urllib.request.urlretrieve(image_url_or_path, dest)
        return
    source = Path(image_url_or_path)
    if source.is_file():
        shutil.copyfile(source, dest)
        return
    raise FileNotFoundError(f"Image output was neither URL nor existing path: {image_url_or_path}")


async def _run(args: argparse.Namespace) -> int:
    from src.media import image_prompt_corpse, images as images_module, get_image_model
    from src.persistence import ImageStore, MemoryStore

    chat_path = Path(args.chat)
    if not chat_path.is_file():
        print(f"Chat file not found: {chat_path}", file=sys.stderr)
        return 1
    chat_text = chat_path.read_text()
    if not chat_text.strip():
        print(f"Chat file is empty: {chat_path}", file=sys.stderr)
        return 1

    output_dir = Path(args.output_dir) / datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    output_dir.mkdir(parents=True, exist_ok=True)
    _setup_logging(output_dir, args.verbose)

    chatbot = _get_chatbot()
    print(f"Chatbot: {chatbot.__class__.__name__}")
    print(f"Chat:    {chat_path} ({len(chat_text.splitlines())} lines)")
    print(f"Output:  {output_dir}\n")

    image_store = ImageStore(args.db)
    memory_store = MemoryStore(args.db)
    server_id = args.server_id

    previous_themes = image_store.get_previous_themes(server_id)
    previous_themes_text = ""
    if previous_themes:
        previous_themes_text = (
            "Please try and avoid repeating themes from the previous image themes. "
            f"Previously used themes are:\n{previous_themes}\n\n"
        )

    all_bios = memory_store.get_all_bios(server_id)
    bios_text = "; ".join(f"{b.user_name}: {b.bio}" for b in all_bios) if all_bios else ""

    decoded = await image_prompt_corpse.build(
        chat_text=chat_text,
        previous_themes_text=previous_themes_text,
        bios_text=bios_text,
        user_locations=os.getenv("USER_LOCATIONS", "").strip(),
        cat_descriptions=os.getenv("CAT_DESCRIPTIONS", "").strip(),
        server_id=server_id,
        image_store=image_store,
        chatbot=chatbot,
        occasion=args.occasion,
    )

    prompt_text = decoded.get("prompt", "")
    themes = decoded.get("themes", [])
    reasoning = decoded.get("reasoning", "")

    prompt_md = (
        "# Assembled prompt\n\n"
        f"{prompt_text}\n\n"
        "## Themes\n\n"
        + ("- " + "\n- ".join(themes) if themes else "_(none)_")
        + "\n\n## Reasoning\n\n"
        f"{reasoning}\n"
    )
    (output_dir / "prompt.md").write_text(prompt_md)

    print("\n=== Assembled prompt ===\n")
    print(prompt_text)
    print(f"\nThemes: {', '.join(themes)}")
    print(f"Reasoning: {reasoning}\n")

    if not args.image:
        print("(Skipping image generation. Pass --image to actually call the model.)")
        print(f"Wrote: {output_dir / 'prompt.md'}")
        print(f"Wrote: {output_dir / 'run.log'}")
        return 0

    model_name = os.getenv("CHAT_IMAGE_MODEL", "") or os.getenv("IMAGE_MODEL", "") or None
    model = get_image_model(model_name)
    print(f"=== Generating image (model: {model.short_name}, cost: ~US${model.cost:.3f}) ===\n")
    full_prompt = prompt_text + f"\n{images_module.get_extra_guidelines()}"
    image_url = await model.generate(full_prompt)
    if not image_url:
        print("Image generation returned no URL/path.", file=sys.stderr)
        return 2

    image_dest = output_dir / "image.png"
    _save_image(image_url, image_dest)
    print(f"Saved: {image_dest}")
    print(f"Wrote: {output_dir / 'prompt.md'}")
    print(f"Wrote: {output_dir / 'run.log'}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Dry-run the corpse image-prompt pipeline against a chat log.",
        epilog="Reads .env from the project root if present. Existing shell env wins.",
    )
    parser.add_argument("chat", help="Path to a chat log file (plain text).")
    parser.add_argument(
        "--image", action="store_true",
        help="Actually generate the image (costs money — usually a few cents).",
    )
    parser.add_argument(
        "--server-id",
        default=os.getenv("DISCORD_SERVER_ID", "dev-try-chat-image"),
        help="Server id for anti-list persistence (default: DISCORD_SERVER_ID env or 'dev-try-chat-image').",
    )
    parser.add_argument(
        "--db", default="./data/gepetto.db",
        help="Sqlite DB path (default: ./data/gepetto.db).",
    )
    parser.add_argument(
        "--output-dir", default="./samples/output",
        help="Parent directory for timestamped run outputs (default: ./samples/output).",
    )
    parser.add_argument(
        "--occasion", default=None,
        help="An 'on this day' directive to inject into the assembler (e.g. a "
             "Brexit-anniversary instruction). Lets you preview an occasion image "
             "without waiting for the date. Free text.",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="DEBUG-level logging.")
    args = parser.parse_args()

    _load_dotenv_if_present()
    return asyncio.run(_run(args))


if __name__ == "__main__":
    sys.exit(main())
