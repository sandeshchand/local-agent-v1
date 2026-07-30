from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from local_agent.app.config import load_config
from local_agent.operations import (
    RuntimeBackupError,
    backup_runtime_state,
    inspect_runtime_backup,
    list_runtime_backups,
    prune_runtime_backups,
    restore_runtime_state,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Back up or restore local runtime state.")
    parser.add_argument("--env-file", default=".env", help="Environment file used to resolve runtime paths.")

    subparsers = parser.add_subparsers(dest="command", required=True)

    backup_parser = subparsers.add_parser("backup", help="Create a runtime backup.")
    backup_parser.add_argument(
        "--backup-root",
        default="",
        help="Directory where timestamped backups are created. Defaults to var/backups under the project root.",
    )
    backup_parser.add_argument(
        "--output-dir",
        default="",
        help="Exact backup directory to create. Must be empty if it already exists.",
    )

    inspect_parser = subparsers.add_parser("inspect", help="Inspect backup metadata.")
    inspect_parser.add_argument("--backup-path", required=True, help="Backup directory to inspect.")

    list_parser = subparsers.add_parser("list-backups", help="List runtime backups.")
    list_parser.add_argument(
        "--backup-root",
        default="",
        help="Directory containing timestamped backups. Defaults to var/backups under the project root.",
    )
    list_parser.add_argument("--limit", type=int, default=0, help="Maximum backups to return. 0 means all.")

    prune_parser = subparsers.add_parser("prune-backups", help="Prune old runtime backups by retention count.")
    prune_parser.add_argument(
        "--backup-root",
        default="",
        help="Directory containing timestamped backups. Defaults to var/backups under the project root.",
    )
    prune_parser.add_argument("--keep", type=int, default=7, help="Number of newest valid backups to keep.")
    prune_parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually delete old backups. Without this flag, the command is a dry run.",
    )

    restore_parser = subparsers.add_parser("restore", help="Restore runtime state from a backup.")
    restore_parser.add_argument("--backup-path", required=True, help="Backup directory to restore.")
    restore_parser.add_argument(
        "--force",
        action="store_true",
        help="Move existing runtime state aside and restore the backup.",
    )

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    config = load_config(args.env_file)

    try:
        if args.command == "backup":
            result = backup_runtime_state(
                sqlite_path=config.sqlite_path,
                qdrant_path=config.qdrant_path,
                backup_root=args.backup_root or None,
                output_dir=args.output_dir or None,
            )
            print(json.dumps(result, indent=2))
            return

        if args.command == "inspect":
            result = inspect_runtime_backup(args.backup_path)
            print(json.dumps(result, indent=2))
            return

        if args.command == "list-backups":
            backups = list_runtime_backups(args.backup_root or None)
            if args.limit > 0:
                backups = backups[: args.limit]
            print(
                json.dumps(
                    {
                        "count": len(backups),
                        "backups": backups,
                    },
                    indent=2,
                )
            )
            return

        if args.command == "prune-backups":
            result = prune_runtime_backups(
                backup_root=args.backup_root or None,
                keep=args.keep,
                dry_run=not args.apply,
            )
            print(json.dumps(result, indent=2))
            return

        if args.command == "restore":
            result = restore_runtime_state(
                backup_path=args.backup_path,
                sqlite_path=config.sqlite_path,
                qdrant_path=config.qdrant_path,
                force=args.force,
            )
            print(json.dumps(result, indent=2))
            return

        raise RuntimeBackupError(f"Unknown command: {args.command}")
    except RuntimeBackupError as exc:
        print(f"Runtime state error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
