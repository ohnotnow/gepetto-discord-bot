#!/usr/bin/env python3
"""Add (or list/edit/delete) an "on this day" chat-image occasion.

An occasion is a per-server (or global) directive injected into the daily
chat-image assembler on a given date — e.g. "reference the Brexit anniversary".
See ant gepettodiscordbot-VXQvH for the design and src/media/image_prompt_corpse.py
for where it lands.

match_key forms:
    2026-06-23   fires once, only on that exact date
    06-23        fires every year on 23 June

Scope:
    --server-id <id>   store against one Discord server (default: $DISCORD_SERVER_ID)
    --global           store as a GLOBAL occasion (applies to every server)

Examples:
    # Open $VISUAL/$EDITOR on a pre-filled template (server_id pre-filled, you
    # write the date + directive):
    uv run python scripts/add_occasion.py --server-id 123456789012345678

    # Fully non-interactive (skips the editor):
    uv run python scripts/add_occasion.py --global --date 12-25 \
        --directive "It is Christmas Day. Give the scene a warm, festive glow."

    uv run python scripts/add_occasion.py --server-id 123 --list
    uv run python scripts/add_occasion.py --global --date 12-25 --delete

    # Edit an existing occasion in $EDITOR (find its id with --list):
    uv run python scripts/add_occasion.py --edit 4

Env loading:
    Reads `.env` from the project root if present (KEY=value lines, # comments
    and blank lines ignored). Existing shell env wins.
"""

import argparse
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.persistence import ImageStore, GLOBAL_SERVER_ID  # noqa: E402

DIRECTIVE_MARKER = "# ===== DIRECTIVE BELOW THIS LINE — free text, kept verbatim ====="

TEMPLATE = """\
# Add a chat-image "on this day" occasion.
#
# Lines beginning with '#' in this header are ignored. Fill in the fields,
# write the directive below the marker line, then save and quit your editor.
# Leave the directive empty (or make no changes) to abort.
#
# server_id : a Discord server id, or {global_sentinel} for a GLOBAL occasion
#             (applies to every server — e.g. Christmas, Liz Truss's birthday).
# match_key : 2026-06-23  -> fires once, only on that exact date
#             06-23       -> fires every year on 23 June
#
{error_block}server_id: {server_id}
match_key: {match_key}

{marker}
{directive}
"""


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


def _validate(server_id: str, match_key: str, directive: str) -> list[str]:
    """Return a list of human-readable validation errors (empty == valid)."""
    errors = []
    if not server_id:
        errors.append("server_id is required")
    if not directive:
        errors.append("directive is empty")
    if not match_key:
        errors.append("match_key is required")
    elif not (re.fullmatch(r"\d{4}-\d{2}-\d{2}", match_key) or re.fullmatch(r"\d{2}-\d{2}", match_key)):
        errors.append("match_key must be YYYY-MM-DD (one-off) or MM-DD (annual)")
    else:
        # Confirm it's a real calendar date. Use leap-year 2000 for MM-DD so
        # 02-29 validates as an annual key.
        probe = match_key if len(match_key) == 10 else f"2000-{match_key}"
        try:
            datetime.strptime(probe, "%Y-%m-%d")
        except ValueError:
            errors.append(f"{match_key} is not a valid calendar date")
    return errors


def _render_template(server_id: str, match_key: str, directive: str, errors=None) -> str:
    error_block = ""
    if errors:
        error_block = "".join(f"# ERROR: {e}\n" for e in errors) + "#\n"
    return TEMPLATE.format(
        global_sentinel=GLOBAL_SERVER_ID,
        error_block=error_block,
        server_id=server_id or "",
        match_key=match_key or "",
        marker=DIRECTIVE_MARKER,
        directive=directive or "",
    )


def _parse_template(text: str) -> tuple[str, str, str]:
    """Split an edited template into (server_id, match_key, directive)."""
    header, _, body = text.partition(DIRECTIVE_MARKER)
    fields = {}
    for line in header.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or ":" not in stripped:
            continue
        key, _, value = stripped.partition(":")
        fields[key.strip().lower()] = value.strip()
    return fields.get("server_id", ""), fields.get("match_key", ""), body.strip()


def _resolve_editor() -> str | None:
    editor = os.environ.get("VISUAL") or os.environ.get("EDITOR")
    if editor:
        return editor
    for candidate in ("nano", "vim", "vi"):
        if shutil.which(candidate):
            return candidate
    return None


def _edit_loop(server_id: str, match_key: str, directive: str):
    """Open the editor until we get a valid occasion or the user aborts.

    Returns (server_id, match_key, directive) on success, or None if aborted.
    On repeated validation failure the draft is preserved on disk so a long
    directive is never lost.
    """
    editor = _resolve_editor()
    if not editor:
        print("No editor found. Set $VISUAL or $EDITOR (e.g. export EDITOR=nano), "
              "or pass --date and --directive to skip the editor.", file=sys.stderr)
        return None

    fd, path = tempfile.mkstemp(suffix=".occasion.txt")
    os.close(fd)
    Path(path).write_text(_render_template(server_id, match_key, directive))

    result = None
    keep_file = False
    try:
        for _ in range(5):
            subprocess.call(shlex.split(editor) + [path])
            sid, mk, directive = _parse_template(Path(path).read_text())
            if not directive:
                print("Aborted (directive left empty).")
                break
            errors = _validate(sid, mk, directive)
            if not errors:
                result = (sid, mk, directive)
                break
            print("Validation failed: " + "; ".join(errors) + " — reopening editor…")
            Path(path).write_text(_render_template(sid, mk, directive, errors))
        else:
            keep_file = True
            print(f"Gave up after several attempts. Your draft is kept at: {path}")
    finally:
        if not keep_file:
            try:
                os.unlink(path)
            except OSError:
                pass
    return result


def _kind(match_key: str) -> str:
    return "annual" if len(match_key) == 5 else "one-off"


def _report(verb: str, server_id: str, match_key: str, directive: str) -> None:
    scope = "GLOBAL (all servers)" if server_id == GLOBAL_SERVER_ID else f"server {server_id}"
    gist = directive if len(directive) <= 200 else directive[:197] + "…"
    print(f"✓ Occasion {verb} for {scope}: {match_key} ({_kind(match_key)})")
    print(f"  {gist}")


def _insert(store: ImageStore, server_id: str, match_key: str, directive: str) -> None:
    store.add_occasion(server_id, match_key, directive)
    _report("saved", server_id, match_key, directive)


def _update(store: ImageStore, occasion_id: int, server_id: str, match_key: str, directive: str) -> None:
    store.update_occasion(occasion_id, server_id, match_key, directive)
    _report("updated", server_id, match_key, directive)


def _print_rows(title: str, rows: list[dict]) -> None:
    print(f"\n{title}:")
    if not rows:
        print("  (none)")
        return
    for row in rows:
        gist = " ".join(row["directive"].split())
        if len(gist) > 80:
            gist = gist[:77] + "…"
        print(f"  #{row['id']:<4} [{row['match_key']}] ({_kind(row['match_key'])}) {gist}")


def main() -> int:
    _load_dotenv_if_present()

    parser = argparse.ArgumentParser(
        description="Add/list/edit/delete an 'on this day' chat-image occasion.",
        epilog="Reads .env from the project root if present. Existing shell env wins.",
    )
    scope = parser.add_mutually_exclusive_group()
    scope.add_argument(
        "--server-id", default=os.getenv("DISCORD_SERVER_ID"),
        help="Discord server id (default: DISCORD_SERVER_ID env).",
    )
    scope.add_argument(
        "--global", dest="is_global", action="store_true",
        help="Store as a GLOBAL occasion that applies to every server.",
    )
    parser.add_argument("--date", default=None, help="match_key: YYYY-MM-DD (once) or MM-DD (annual).")
    parser.add_argument("--directive", default=None, help="The directive text. Omit to open an editor.")
    parser.add_argument("--db", default="./data/gepetto.db", help="Sqlite DB path (default: ./data/gepetto.db).")
    parser.add_argument("--list", action="store_true", help="List occasions (with ids) for the scope and exit.")
    parser.add_argument("--edit", type=int, default=None, metavar="ID",
                        help="Edit the occasion with this id (from --list) in $EDITOR, then update it in place.")
    parser.add_argument("--delete", action="store_true", help="Delete the occasion for --date in the scope and exit.")
    args = parser.parse_args()

    store = ImageStore(args.db)
    scope_id = GLOBAL_SERVER_ID if args.is_global else args.server_id

    if args.list:
        if args.is_global:
            _print_rows("Global occasions (apply to all servers)", store.list_occasions(GLOBAL_SERVER_ID))
        else:
            if scope_id:
                _print_rows(f"Occasions for server {scope_id}", store.list_occasions(scope_id))
            else:
                print("(no --server-id given; showing globals only)")
            _print_rows("Global occasions (apply to all servers)", store.list_occasions(GLOBAL_SERVER_ID))
        return 0

    if args.edit is not None:
        existing = store.get_occasion_by_id(args.edit)
        if not existing:
            print(f"No occasion with id {args.edit}. Run --list to see ids.", file=sys.stderr)
            return 1
        result = _edit_loop(existing["server_id"], existing["match_key"], existing["directive"])
        if not result:
            return 1
        sid, match_key, directive = result
        _update(store, args.edit, sid, match_key, directive)
        return 0

    if args.delete:
        if not scope_id:
            print("Need --server-id or --global to delete.", file=sys.stderr)
            return 1
        if not args.date:
            print("Need --date to identify which occasion to delete.", file=sys.stderr)
            return 1
        deleted = store.delete_occasion(scope_id, args.date.strip())
        scope = "GLOBAL" if args.is_global else f"server {scope_id}"
        print(f"Deleted {deleted} occasion(s) for {scope} on {args.date.strip()}.")
        return 0

    # Add path. Skip the editor only when scope + date + directive are all given.
    if scope_id and args.date and args.directive:
        match_key = args.date.strip()
        errors = _validate(scope_id, match_key, args.directive)
        if errors:
            print("Cannot add occasion: " + "; ".join(errors), file=sys.stderr)
            return 1
        _insert(store, scope_id, match_key, args.directive)
        return 0

    result = _edit_loop(scope_id or "", (args.date or "").strip(), args.directive or "")
    if not result:
        return 1
    sid, match_key, directive = result
    _insert(store, sid, match_key, directive)
    return 0


if __name__ == "__main__":
    sys.exit(main())
