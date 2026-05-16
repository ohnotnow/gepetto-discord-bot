#!/usr/bin/env python3
"""Dev tool for iterating on the news-bulletin pipeline.

Thin wrapper around `src.content.news` — fetches BBC RSS, runs the
keyword cull, optionally calls the LLM for editorial synthesis, and
optionally feeds the bulletins through the corpse pipeline to preview
an image. Domain logic lives in the module; this script is just a
pretty-printer + CLI.

Examples:
    uv run python scripts/try_news_filter.py
    uv run python scripts/try_news_filter.py --llm
    uv run python scripts/try_news_filter.py --llm --image
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

from src.content.news import (  # noqa: E402  (sys.path tweak above)
    FEEDS,
    GRIM_KEYWORDS,
    Bulletin,
    Item,
    clean_summary,
    dedupe,
    fetch_feed,
    grim_match,
    synthesise_bulletins,
)


def _load_dotenv_if_present() -> None:
    env_path = PROJECT_ROOT / ".env"
    if not env_path.is_file():
        return
    for raw in env_path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        os.environ.setdefault(key, value)


def _get_chatbot():
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


def _setup_image_logging(output_dir: Path) -> None:
    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)-7s %(name)s %(message)s",
        datefmt="%H:%M:%S",
    )
    file_handler = logging.FileHandler(output_dir / "run.log", mode="w")
    file_handler.setFormatter(formatter)
    discord_logger = logging.getLogger("discord")
    discord_logger.setLevel(logging.INFO)
    discord_logger.addHandler(file_handler)
    discord_logger.propagate = False
    logging.getLogger("LiteLLM").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)


async def run_corpse_from_bulletins(
    bulletins: list[Bulletin],
    *,
    output_dir: Path,
    server_id: str,
    db_path: str,
    make_image: bool,
) -> None:
    """Feed the bulletins into build_quiet() via its news_bulletins kwarg,
    save the assembled prompt to prompt.md, and (when make_image=True) generate
    the actual image into image.png.

    Caveat: build_quiet()'s pickers tell the LLM not to name specific people
    — bulletins contain names which the picker will strip. The image will
    reflect the *flavour* of the day's news, not literal news content.
    """
    from src.media import image_prompt_corpse, images as images_module, get_image_model
    from src.persistence import ImageStore, MemoryStore

    output_dir.mkdir(parents=True, exist_ok=True)
    _setup_image_logging(output_dir)

    chatbot = _get_chatbot()
    image_store = ImageStore(db_path)
    MemoryStore(db_path)  # ensures schema exists if pointed at a fresh DB

    print(f"\n=== Feeding {len(bulletins)} bulletin(s) into build_quiet() ===")
    for b in bulletins:
        print(f"  - {b.heading}: {b.body}")

    previous_themes = image_store.get_previous_themes(server_id)
    previous_themes_text = ""
    if previous_themes:
        previous_themes_text = (
            "Please try and avoid repeating themes from the previous image themes. "
            f"Previously used themes are:\n{previous_themes}\n\n"
        )

    decoded = await image_prompt_corpse.build_quiet(
        bios=[],
        memories=[],
        news_bulletins=bulletins,
        previous_themes_text=previous_themes_text,
        bios_text="",
        user_locations=os.getenv("USER_LOCATIONS", "").strip(),
        cat_descriptions=os.getenv("CAT_DESCRIPTIONS", "").strip(),
        server_id=server_id,
        image_store=image_store,
        chatbot=chatbot,
    )

    prompt_text = decoded.get("prompt", "")
    themes = decoded.get("themes", [])
    reasoning = decoded.get("reasoning", "")

    prompt_md = (
        "# Assembled prompt (news bulletins → build_quiet)\n\n"
        f"{prompt_text}\n\n"
        "## Themes\n\n"
        + ("- " + "\n- ".join(themes) if themes else "_(none)_")
        + "\n\n## Reasoning\n\n"
        f"{reasoning}\n\n"
        "## Source bulletins\n\n"
        + "\n".join(f"- **{b.heading}**: {b.body}" for b in bulletins)
        + "\n"
    )
    (output_dir / "prompt.md").write_text(prompt_md)

    print("\n=== Assembled prompt ===\n")
    print(prompt_text)
    print(f"\nThemes: {', '.join(themes)}")
    print(f"Reasoning: {reasoning}")
    print(f"\nWrote: {output_dir / 'prompt.md'}")
    print(f"Wrote: {output_dir / 'run.log'}")

    if not make_image:
        print("(Skipping image generation. Pass --image to actually call the model.)")
        return

    model_name = os.getenv("CHAT_IMAGE_MODEL", "") or os.getenv("IMAGE_MODEL", "") or None
    model = get_image_model(model_name)
    print(f"\n=== Generating image (model: {model.short_name}, cost: ~US${model.cost:.3f}) ===")
    full_prompt = prompt_text + f"\n{images_module.get_extra_guidelines()}"
    image_url = await model.generate(full_prompt)
    if not image_url:
        print("Image generation returned no URL/path.", file=sys.stderr)
        return
    image_dest = output_dir / "image.png"
    _save_image(image_url, image_dest)
    print(f"Saved: {image_dest}")


async def main() -> int:
    _load_dotenv_if_present()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--feed",
        choices=list(FEEDS.keys()),
        action="append",
        help="Only fetch named feed(s). Default: all four.",
    )
    parser.add_argument(
        "--only-culled",
        action="store_true",
        help="Print only the items the keyword filter would cull.",
    )
    parser.add_argument(
        "--only-kept",
        action="store_true",
        help="Print only the items that survive the filter.",
    )
    default_output = PROJECT_ROOT / "samples" / "news.txt"
    parser.add_argument(
        "--output",
        type=Path,
        default=default_output,
        help=f"Write results to this file (default: {default_output.relative_to(PROJECT_ROOT)}).",
    )
    parser.add_argument(
        "--per-feed",
        type=int,
        default=10,
        help="Max entries to pull from each feed (default: 10).",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="Also echo results to stdout (file is always written).",
    )
    parser.add_argument(
        "--llm",
        action="store_true",
        help="Run keyword-survivors through a single batched LLM call for editorial synthesis.",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Override the model used for --llm (default: BOT_MODEL env var via GPTModel).",
    )
    parser.add_argument(
        "--max-bulletins",
        type=int,
        default=5,
        help="Maximum number of themed bulletins the LLM should produce (default: 5).",
    )
    parser.add_argument(
        "--image",
        action="store_true",
        help="Feed the bulletins into build_quiet() and generate an actual image. Costs an image API call.",
    )
    parser.add_argument(
        "--prompt-only",
        action="store_true",
        help="Like --image but stop after producing the prompt; don't call the image model.",
    )
    parser.add_argument(
        "--db",
        type=str,
        default=str(PROJECT_ROOT / "data" / "gepetto.db"),
        help="Path to the SQLite DB (for anti-list / previous-themes lookups). Default: data/gepetto.db.",
    )
    parser.add_argument(
        "--server-id",
        type=str,
        default="news_test",
        help="Server ID to use for anti-list namespacing (default: news_test, kept separate from real servers).",
    )
    parser.add_argument(
        "--image-output-dir",
        type=Path,
        default=PROJECT_ROOT / "samples" / "news_image",
        help="Parent directory for per-run image outputs (default: samples/news_image).",
    )
    args = parser.parse_args()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []

    def emit(line: str) -> None:
        lines.append(line)
        if args.stdout:
            print(line)

    feeds_to_fetch = args.feed or list(FEEDS.keys())
    all_items: list[Item] = []
    for name in feeds_to_fetch:
        url = FEEDS[name]
        emit(f"[fetch] {name}: {url}")
        items = fetch_feed(name, url, per_feed=args.per_feed)
        emit(f"        {len(items)} entries (capped at {args.per_feed})")
        all_items.extend(items)

    deduped = dedupe(all_items)
    emit(f"\n[dedupe] {len(all_items)} -> {len(deduped)} unique\n")

    survivors: list[Item] = []
    culled = 0
    for item in deduped:
        match = grim_match(item)
        summary = clean_summary(item.summary)
        if match:
            culled += 1
            if not args.only_kept:
                emit(f"  CULL [{item.feed}]  (matched {match!r})  {item.title}")
                if summary:
                    emit(f"         summary: {summary}")
        else:
            survivors.append(item)
            if not args.only_culled:
                emit(f"  KEEP [{item.feed}]  {item.title}")
                if summary:
                    emit(f"         summary: {summary}")

    emit(
        f"\n[keyword-summary] kept={len(survivors)} culled={culled} "
        f"keywords={GRIM_KEYWORDS}"
    )

    bulletins: list[Bulletin] = []
    if args.llm and survivors:
        emit(f"\n[llm] sending {len(survivors)} survivors to model (max {args.max_bulletins} bulletins)...")
        chatbot = _get_chatbot()
        bulletins = await synthesise_bulletins(
            survivors,
            chatbot,
            max_bulletins=args.max_bulletins,
            model=args.model,
        )
        total_sources = sum(len(b.sources) for b in bulletins)
        emit(f"[llm] model returned {len(bulletins)} bulletin(s) drawing on {total_sources} item(s)\n")
        kept_titles: set[str] = set()
        for bulletin in bulletins:
            emit(f"  BULLETIN: {bulletin.heading}  ({len(bulletin.sources)} source{'s' if len(bulletin.sources) != 1 else ''})")
            emit(f"     {bulletin.body}")
            emit("     sources:")
            for item in bulletin.sources:
                kept_titles.add(item.title)
                emit(f"       [{item.feed}] {item.title}")
                summary = clean_summary(item.summary)
                if summary:
                    emit(f"          summary: {summary}")
            emit("")
        dropped = [s for s in survivors if s.title not in kept_titles]
        if dropped:
            emit(f"[llm-dropped] {len(dropped)} headline(s) the model didn't draw on:")
            for item in dropped:
                emit(f"  DROP [{item.feed}]  {item.title}")
                summary = clean_summary(item.summary)
                if summary:
                    emit(f"         summary: {summary}")
        emit(
            f"\n[llm-summary] bulletins={len(bulletins)} items_used={total_sources} "
            f"dropped={len(dropped)}"
        )

    args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {len(lines)} lines to {args.output.relative_to(PROJECT_ROOT)}")

    if (args.image or args.prompt_only) and args.llm:
        if not bulletins:
            print("No bulletins to feed into the corpse pipeline; skipping.", file=sys.stderr)
            return 0
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        run_dir = args.image_output_dir / timestamp
        await run_corpse_from_bulletins(
            bulletins,
            output_dir=run_dir,
            server_id=args.server_id,
            db_path=args.db,
            make_image=args.image,
        )
    elif args.image or args.prompt_only:
        print("--image / --prompt-only require --llm (need bulletins to feed forward).", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
