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
DEFAULT_BACKUP_JOB_LOG = PROJECT_ROOT / "var" / "logs" / "scheduled_backup.jsonl"


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


def list_runtime_backups(
    backup_root: str | Path | None = None,
) -> list[dict[str, Any]]:
    root = _resolve_backup_root(backup_root)
    if not root.exists():
        return []
    if not root.is_dir():
        raise RuntimeBackupError(f"Backup root is not a directory: {root}")

    backups: list[dict[str, Any]] = []
    for candidate in sorted(root.iterdir()):
        if not candidate.is_dir():
            continue
        metadata_path = candidate / "metadata.json"
        if not metadata_path.exists():
            continue
        try:
            backups.append(_backup_summary(inspect_runtime_backup(candidate)))
        except RuntimeBackupError as exc:
            backups.append(
                {
                    "valid": False,
                    "backup_path": str(candidate.resolve()),
                    "created_at": "",
                    "error": str(exc),
                    "total_size_bytes": _directory_size(candidate),
                }
            )

    backups.sort(key=_backup_sort_key, reverse=True)
    return backups


def prune_runtime_backups(
    *,
    backup_root: str | Path | None = None,
    keep: int = 7,
    dry_run: bool = True,
) -> dict[str, Any]:
    if keep < 0:
        raise RuntimeBackupError("--keep must be zero or greater.")

    root = _resolve_backup_root(backup_root)
    backups = [backup for backup in list_runtime_backups(root) if backup.get("valid")]
    kept = backups[:keep]
    candidates = backups[keep:]

    deleted: list[dict[str, Any]] = []
    for backup in candidates:
        backup_dir = Path(str(backup["backup_path"])).resolve()
        _assert_backup_child(root=root, backup_dir=backup_dir)
        deleted.append(backup)
        if not dry_run:
            shutil.rmtree(backup_dir)

    action_key = "would_delete" if dry_run else "deleted"
    return {
        "backup_root": str(root),
        "keep": keep,
        "dry_run": dry_run,
        "found_count": len(backups),
        "kept_count": len(kept),
        f"{action_key}_count": len(deleted),
        "kept": kept,
        action_key: deleted,
    }


def copy_runtime_backup(
    *,
    backup_path: str | Path,
    off_machine_root: str | Path,
) -> dict[str, Any]:
    source_dir = Path(backup_path).expanduser().resolve()
    metadata = inspect_runtime_backup(source_dir)
    root = Path(off_machine_root).expanduser().resolve()
    if _path_is_relative_to(root, source_dir):
        raise RuntimeBackupError(
            f"Off-machine root cannot be inside the backup directory: {root}"
        )
    if _path_is_relative_to(root, source_dir.parent):
        raise RuntimeBackupError(
            f"Off-machine root cannot be inside the local backup root: {root}"
        )
    root.mkdir(parents=True, exist_ok=True)

    dest_dir = root / source_dir.name
    if dest_dir.exists():
        raise RuntimeBackupError(f"Off-machine backup destination already exists: {dest_dir}")

    shutil.copytree(source_dir, dest_dir)
    copied_metadata = inspect_runtime_backup(dest_dir)
    summary = _backup_summary(copied_metadata)
    summary["copied"] = True
    summary["source_backup_path"] = metadata.get("backup_path", str(source_dir))
    summary["off_machine_root"] = str(root)
    return summary


def run_scheduled_backup(
    *,
    sqlite_path: str | Path,
    qdrant_path: str | Path,
    backup_root: str | Path | None = None,
    off_machine_root: str | Path | None = None,
    local_keep: int = 14,
    off_machine_keep: int = 28,
    apply_prune: bool = False,
    job_log_path: str | Path | None = DEFAULT_BACKUP_JOB_LOG,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "status": "running",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "completed_at": "",
        "backup": {},
        "off_machine_copy": {},
        "local_prune": {},
        "off_machine_prune": {},
        "warnings": [],
        "error": "",
    }

    try:
        backup = backup_runtime_state(
            sqlite_path=sqlite_path,
            qdrant_path=qdrant_path,
            backup_root=backup_root,
        )
        result["backup"] = _backup_summary(inspect_runtime_backup(backup["backup_path"]))

        if off_machine_root:
            result["off_machine_copy"] = copy_runtime_backup(
                backup_path=backup["backup_path"],
                off_machine_root=off_machine_root,
            )
        else:
            result["warnings"].append(
                "No off-machine root configured; backup was created locally only."
            )

        result["local_prune"] = prune_runtime_backups(
            backup_root=backup_root,
            keep=local_keep,
            dry_run=not apply_prune,
        )
        if off_machine_root:
            result["off_machine_prune"] = prune_runtime_backups(
                backup_root=off_machine_root,
                keep=off_machine_keep,
                dry_run=not apply_prune,
            )

        result["status"] = "success"
        return result
    except Exception as exc:
        result["status"] = "failed"
        result["error"] = str(exc)
        if isinstance(exc, RuntimeBackupError):
            raise
        raise RuntimeBackupError(str(exc)) from exc
    finally:
        result["completed_at"] = datetime.now(timezone.utc).isoformat()
        if job_log_path is not None:
            result["job_log_path"] = _append_backup_job_log(job_log_path, result)


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


def _resolve_backup_root(backup_root: str | Path | None) -> Path:
    return Path(backup_root).expanduser().resolve() if backup_root else DEFAULT_BACKUP_ROOT


def _append_backup_job_log(path: str | Path, payload: dict[str, Any]) -> str:
    log_path = Path(path).expanduser()
    if not log_path.is_absolute():
        log_path = PROJECT_ROOT / log_path
    log_path = log_path.resolve()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")
    return str(log_path)


def _path_is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _backup_summary(metadata: dict[str, Any]) -> dict[str, Any]:
    artifacts = metadata.get("artifacts", {})
    sqlite_artifact = artifacts.get("sqlite", {})
    qdrant_artifact = artifacts.get("qdrant", {})
    sqlite_size = int(sqlite_artifact.get("size_bytes") or 0)
    qdrant_size = int(qdrant_artifact.get("size_bytes") or 0)
    return {
        "valid": True,
        "backup_path": metadata.get("backup_path", ""),
        "created_at": metadata.get("created_at", ""),
        "format_version": metadata.get("format_version"),
        "sqlite_exists": bool(sqlite_artifact.get("exists")),
        "qdrant_exists": bool(qdrant_artifact.get("exists")),
        "sqlite_size_bytes": sqlite_size,
        "qdrant_size_bytes": qdrant_size,
        "qdrant_file_count": int(qdrant_artifact.get("file_count") or 0),
        "total_size_bytes": sqlite_size + qdrant_size,
        "source": metadata.get("source", {}),
    }


def _backup_sort_key(backup: dict[str, Any]) -> tuple[str, str]:
    return (
        str(backup.get("created_at") or ""),
        str(backup.get("backup_path") or ""),
    )


def _assert_backup_child(*, root: Path, backup_dir: Path) -> None:
    resolved_root = root.resolve()
    resolved_backup_dir = backup_dir.resolve()
    if resolved_backup_dir.parent != resolved_root:
        raise RuntimeBackupError(
            f"Refusing to prune a path outside the backup root: {resolved_backup_dir}"
        )
    if not (resolved_backup_dir / "metadata.json").exists():
        raise RuntimeBackupError(
            f"Refusing to prune a directory without backup metadata: {resolved_backup_dir}"
        )


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
