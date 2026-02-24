"""
Backup and restore server data for migration between bot instances.

Usage:
    uv run python backup_restore.py sections
    uv run python backup_restore.py export SERVER_ID [--gzip] [--include a,b] [--exclude a,b]
    uv run python backup_restore.py import FILE [--server-id NEW_ID] [--include a,b] [--exclude a,b]
"""

import argparse
import gzip
import json
import sys
from datetime import datetime

from src.persistence import get_backup_stores


def get_all_sections(stores: list) -> dict:
    """Collect all backup sections from all stores."""
    sections = {}
    for store in stores:
        sections.update(store.backup_sections())
    return sections


def get_store_for_section(stores: list, section: str):
    """Find the store that owns a given section."""
    for store in stores:
        if section in store.backup_sections():
            return store
    return None


def cmd_sections(_args):
    """List all available backup sections."""
    stores = get_backup_stores()
    sections = get_all_sections(stores)

    print("Available backup sections:\n")
    for name, description in sorted(sections.items()):
        print(f"  {name:15s} {description}")


def cmd_export(args):
    """Export server data to a JSON file."""
    stores = get_backup_stores()
    all_sections = get_all_sections(stores)

    # Determine which sections to export
    if args.include:
        requested = set(args.include.split(","))
        unknown = requested - set(all_sections)
        if unknown:
            print(f"Error: unknown sections: {', '.join(sorted(unknown))}")
            print(f"Available: {', '.join(sorted(all_sections))}")
            sys.exit(1)
        sections_to_export = requested
    elif args.exclude:
        excluded = set(args.exclude.split(","))
        unknown = excluded - set(all_sections)
        if unknown:
            print(f"Error: unknown sections: {', '.join(sorted(unknown))}")
            print(f"Available: {', '.join(sorted(all_sections))}")
            sys.exit(1)
        sections_to_export = set(all_sections) - excluded
    else:
        sections_to_export = set(all_sections)

    # Export data from each relevant store
    exported_data = {
        "server_id": args.server_id,
        "exported_at": datetime.now().isoformat(),
        "sections": {},
    }

    for store in stores:
        store_sections = set(store.backup_sections()) & sections_to_export
        if not store_sections:
            continue

        result = store.export_server(args.server_id)
        for section in store_sections:
            if section in result:
                exported_data["sections"][section] = result[section]

    # Write output
    json_str = json.dumps(exported_data, indent=2, ensure_ascii=False)

    if args.gzip:
        filename = f"{args.server_id}_backup.json.gz"
        with gzip.open(filename, "wt", encoding="utf-8") as f:
            f.write(json_str)
    else:
        filename = f"{args.server_id}_backup.json"
        with open(filename, "w", encoding="utf-8") as f:
            f.write(json_str)

    # Print summary
    total = sum(len(v) for v in exported_data["sections"].values())
    section_counts = ", ".join(
        f"{len(v)} {k}" for k, v in sorted(exported_data["sections"].items())
    )
    print(f"Exported {total} records ({section_counts}) to {filename}")


def cmd_import(args):
    """Import server data from a JSON file."""
    # Read input
    filename = args.file
    if filename.endswith(".gz"):
        with gzip.open(filename, "rt", encoding="utf-8") as f:
            data = json.load(f)
    else:
        with open(filename, "r", encoding="utf-8") as f:
            data = json.load(f)

    server_id = args.server_id or data["server_id"]
    stores = get_backup_stores()
    all_sections = get_all_sections(stores)

    # Determine which sections to import
    available_in_file = set(data.get("sections", {}).keys())

    if args.include:
        requested = set(args.include.split(","))
        unknown = requested - set(all_sections)
        if unknown:
            print(f"Error: unknown sections: {', '.join(sorted(unknown))}")
            sys.exit(1)
        sections_to_import = requested & available_in_file
    elif args.exclude:
        excluded = set(args.exclude.split(","))
        sections_to_import = available_in_file - excluded
    else:
        sections_to_import = available_in_file

    # Import data into each relevant store
    all_results = {}
    for store in stores:
        store_sections = set(store.backup_sections()) & sections_to_import
        if not store_sections:
            continue

        # Build data dict with only the sections this store handles
        store_data = {s: data["sections"][s] for s in store_sections if s in data["sections"]}
        if store_data:
            result = store.import_server(server_id, store_data)
            all_results.update(result)

    # Print summary
    parts = []
    for section, counts in sorted(all_results.items()):
        imported = counts["imported"]
        skipped = counts["skipped"]
        skip_str = f" ({skipped} skipped)" if skipped else ""
        parts.append(f"{imported} {section}{skip_str}")

    if parts:
        print(f"Imported into server {server_id}: {', '.join(parts)}")
    else:
        print("Nothing to import.")


def main():
    parser = argparse.ArgumentParser(
        description="Backup and restore server data for migration between bot instances."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # sections command
    subparsers.add_parser("sections", help="List available backup sections")

    # export command
    export_parser = subparsers.add_parser("export", help="Export server data")
    export_parser.add_argument("server_id", help="Discord server ID to export")
    export_parser.add_argument("--gzip", action="store_true", help="Compress output with gzip")
    export_group = export_parser.add_mutually_exclusive_group()
    export_group.add_argument("--include", help="Comma-separated sections to include")
    export_group.add_argument("--exclude", help="Comma-separated sections to exclude")

    # import command
    import_parser = subparsers.add_parser("import", help="Import server data")
    import_parser.add_argument("file", help="Backup file to import")
    import_parser.add_argument("--server-id", help="Override server ID (for migration)")
    import_group = import_parser.add_mutually_exclusive_group()
    import_group.add_argument("--include", help="Comma-separated sections to include")
    import_group.add_argument("--exclude", help="Comma-separated sections to exclude")

    args = parser.parse_args()

    if args.command == "sections":
        cmd_sections(args)
    elif args.command == "export":
        cmd_export(args)
    elif args.command == "import":
        cmd_import(args)


if __name__ == "__main__":
    main()
