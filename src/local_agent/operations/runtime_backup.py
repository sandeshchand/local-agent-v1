from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import sqlite3
from typing import Any

from local_agent.app.paths import PROJECT_ROOT


BACKUP_FORMAT_VERSION = 1
DEFAULT_BACKUP_ROOT = PROJECT_ROOT / "var" / "backups"


class RuntimeBackupError(RuntimeError):
    """Raised when runtime backup or restore cannot be completed safely."""


def backup_runtime_state(
    *,
    sqlite_path: str | Path,
    qdrant_path: str | Path,
    backup_root: str | Path | None = None,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    backup_dir = _prepare_backup_dir(backup_root=backup_root, output_dir=output_dir)
    sqlite_source = Path(sqlite_path).expanduser().resolve()
    qdrant_source = Path(qdrant_path).expanduser().resolve()

    metadata: dict[str, Any] = {
        "format_version": BACKUP_FORMAT_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "sqlite_path": str(sqlite_source),
            "qdrant_path": str(qdrant_source),
        },
        "artifacts": {},
    }

    sqlite_dest = backup_dir / "sqlite" / "app.db"
    sqlite_artifact = _backup_sqlite(sqlite_source, sqlite_dest)
    metadata["artifacts"]["sqlite"] = sqlite_artifact

    qdrant_dest = backup_dir / "qdrant"
    qdrant_artifact = _backup_qdrant(qdrant_source, qdrant_dest)
    metadata["artifacts"]["qdrant"] = qdrant_artifact

    metadata_path = backup_dir / "metadata.json"
    metadata["backup_path"] = str(backup_dir)
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return metadata


def restore_runtime_state(
    *,
    backup_path: str | Path,
    sqlite_path: str | Path,
    qdrant_path: str | Path,
    force: bool = False,
) -> dict[str, Any]:
    backup_dir = Path(backup_path).expanduser().resolve()
    metadata = inspect_runtime_backup(backup_dir)

    sqlite_target = Path(sqlite_path).expanduser().resolve()
    qdrant_target = Path(qdrant_path).expanduser().resolve()
    restore_started_at = _timestamp()
    restored: dict[str, Any] = {
        "backup_path": str(backup_dir),
        "restored_at": datetime.now(timezone.utc).isoformat(),
        "artifacts": {},
    }

    sqlite_artifact = metadata.get("artifacts", {}).get("sqlite", {})
    qdrant_artifact = metadata.get("artifacts", {}).get("qdrant", {})
    _preflight_restore(
        backup_dir=backup_dir,
        sqlite_artifact=sqlite_artifact,
        qdrant_artifact=qdrant_artifact,
        sqlite_target=sqlite_target,
        qdrant_target=qdrant_target,
        force=force,
    )

    if sqlite_artifact.get("exists"):
        sqlite_backup = backup_dir / sqlite_artifact.get("relative_path", "sqlite/app.db")
        restored["artifacts"]["sqlite"] = _restore_file(
            source=sqlite_backup,
            target=sqlite_target,
            force=force,
            timestamp=restore_started_at,
        )
    else:
        restored["artifacts"]["sqlite"] = {"restored": False, "reason": "SQLite artifact not present."}

    if qdrant_artifact.get("exists"):
        qdrant_backup = backup_dir / qdrant_artifact.get("relative_path", "qdrant")
        restored["artifacts"]["qdrant"] = _restore_directory(
            source=qdrant_backup,
            target=qdrant_target,
            force=force,
            timestamp=restore_started_at,
        )
    else:
        restored["artifacts"]["qdrant"] = {"restored": False, "reason": "Qdrant artifact not present."}

    return restored


def inspect_runtime_backup(backup_path: str | Path) -> dict[str, Any]:
    backup_dir = Path(backup_path).expanduser().resolve()
    metadata_path = backup_dir / "metadata.json"
    if not metadata_path.exists():
        raise RuntimeBackupError(f"Backup metadata not found: {metadata_path}")

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if metadata.get("format_version") != BACKUP_FORMAT_VERSION:
        raise RuntimeBackupError(
            f"Unsupported backup format: {metadata.get('format_version')}"
        )
    metadata["backup_path"] = str(backup_dir)
    return metadata


def _prepare_backup_dir(
    *,
    backup_root: str | Path | None,
    output_dir: str | Path | None,
) -> Path:
    if output_dir is not None:
        backup_dir = Path(output_dir).expanduser().resolve()
        if backup_dir.exists() and any(backup_dir.iterdir()):
            raise RuntimeBackupError(f"Backup output directory is not empty: {backup_dir}")
        backup_dir.mkdir(parents=True, exist_ok=True)
        return backup_dir

    root = Path(backup_root).expanduser().resolve() if backup_root else DEFAULT_BACKUP_ROOT
    root.mkdir(parents=True, exist_ok=True)
    backup_dir = root / f"local_agent_backup_{_timestamp()}"
    suffix = 1
    while backup_dir.exists():
        backup_dir = root / f"local_agent_backup_{_timestamp()}_{suffix}"
        suffix += 1
    backup_dir.mkdir(parents=True)
    return backup_dir


def _backup_sqlite(source: Path, dest: Path) -> dict[str, Any]:
    if not source.exists():
        return {
            "exists": False,
            "relative_path": "sqlite/app.db",
            "message": "SQLite database file was not found.",
        }

    dest.parent.mkdir(parents=True, exist_ok=True)
    source_conn: sqlite3.Connection | None = None
    dest_conn: sqlite3.Connection | None = None
    try:
        source_uri = f"{source.as_uri()}?mode=ro"
        source_conn = sqlite3.connect(source_uri, uri=True)
        dest_conn = sqlite3.connect(str(dest))
        source_conn.backup(dest_conn)
    finally:
        if dest_conn is not None:
            dest_conn.close()
        if source_conn is not None:
            source_conn.close()

    return {
        "exists": True,
        "relative_path": "sqlite/app.db",
        "size_bytes": dest.stat().st_size,
    }


def _backup_qdrant(source: Path, dest: Path) -> dict[str, Any]:
    if not source.exists():
        return {
            "exists": False,
            "relative_path": "qdrant",
            "message": "Qdrant directory was not found.",
        }
    if not source.is_dir():
        raise RuntimeBackupError(f"Qdrant path is not a directory: {source}")

    shutil.copytree(
        source,
        dest,
        ignore=shutil.ignore_patterns(".lock", "*.lock"),
    )
    return {
        "exists": True,
        "relative_path": "qdrant",
        "lock_file_present": (source / ".lock").exists(),
        "file_count": _count_files(dest),
        "size_bytes": _directory_size(dest),
    }


def _preflight_restore(
    *,
    backup_dir: Path,
    sqlite_artifact: dict[str, Any],
    qdrant_artifact: dict[str, Any],
    sqlite_target: Path,
    qdrant_target: Path,
    force: bool,
) -> None:
    if sqlite_artifact.get("exists"):
        sqlite_backup = backup_dir / sqlite_artifact.get("relative_path", "sqlite/app.db")
        if not sqlite_backup.exists():
            raise RuntimeBackupError(f"Backup file does not exist: {sqlite_backup}")
        if sqlite_target.exists() and not force:
            raise RuntimeBackupError(f"Target file already exists. Re-run with --force: {sqlite_target}")

    if qdrant_artifact.get("exists"):
        qdrant_backup = backup_dir / qdrant_artifact.get("relative_path", "qdrant")
        if not qdrant_backup.exists() or not qdrant_backup.is_dir():
            raise RuntimeBackupError(f"Backup directory does not exist: {qdrant_backup}")
        if qdrant_target.exists():
            target_is_empty_directory = qdrant_target.is_dir() and not any(qdrant_target.iterdir())
            if not target_is_empty_directory and not force:
                raise RuntimeBackupError(
                    f"Target directory already exists. Re-run with --force: {qdrant_target}"
                )


def _restore_file(
    *,
    source: Path,
    target: Path,
    force: bool,
    timestamp: str,
) -> dict[str, Any]:
    if not source.exists():
        raise RuntimeBackupError(f"Backup file does not exist: {source}")

    moved_existing = ""
    if target.exists():
        if not force:
            raise RuntimeBackupError(f"Target file already exists. Re-run with --force: {target}")
        moved_existing = str(_move_existing(target, timestamp))

    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    return {
        "restored": True,
        "target_path": str(target),
        "moved_existing_to": moved_existing,
        "size_bytes": target.stat().st_size,
    }


def _restore_directory(
    *,
    source: Path,
    target: Path,
    force: bool,
    timestamp: str,
) -> dict[str, Any]:
    if not source.exists() or not source.is_dir():
        raise RuntimeBackupError(f"Backup directory does not exist: {source}")

    moved_existing = ""
    if target.exists():
        if target.is_dir() and not any(target.iterdir()):
            target.rmdir()
        elif not force:
            raise RuntimeBackupError(f"Target directory already exists. Re-run with --force: {target}")
        else:
            moved_existing = str(_move_existing(target, timestamp))

    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, target)
    return {
        "restored": True,
        "target_path": str(target),
        "moved_existing_to": moved_existing,
        "file_count": _count_files(target),
        "size_bytes": _directory_size(target),
    }


def _move_existing(path: Path, timestamp: str) -> Path:
    target = path.with_name(f"{path.name}.pre_restore_{timestamp}")
    suffix = 1
    while target.exists():
        target = path.with_name(f"{path.name}.pre_restore_{timestamp}_{suffix}")
        suffix += 1
    shutil.move(str(path), str(target))
    return target


def _directory_size(path: Path) -> int:
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def _count_files(path: Path) -> int:
    return sum(1 for item in path.rglob("*") if item.is_file())


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")
