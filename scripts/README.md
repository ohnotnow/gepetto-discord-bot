# Purpose

This is the place to put test/debug/playground scripts to try out ideas without going straight into the depths of the code.

## Scripts

- **`try_chat_image.py`** — dry-run the daily chat-image corpse pipeline against a chat log on disk (free unless `--image`). Supports `--occasion "<text>"` to preview an "on this day" image.
- **`try_news_filter.py`** — exercise the news-filtering pipeline.
- **`add_occasion.py`** — add/list/edit/delete "on this day" chat-image occasions (date-keyed prompt directives). Opens `$EDITOR` on a pre-filled template, or runs non-interactively if `--server-id`/`--date`/`--directive` (or `--global`) are all supplied. `--list` shows each occasion's id; `--edit <id>` reopens it in `$EDITOR` and updates it in place. See the README's "On this day image occasions" section.


