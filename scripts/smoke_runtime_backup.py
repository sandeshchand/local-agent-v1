from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

from local_agent.operations import (
    backup_runtime_state,
    inspect_runtime_backup,
    list_runtime_backups,
    prune_runtime_backups,
    restore_runtime_state,
)


def write_sqlite_value(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS probe (value TEXT NOT NULL)")
        conn.execute("DELETE FROM probe")
        conn.execute("INSERT INTO probe (value) VALUES (?)", (value,))
        conn.commit()
    finally:
        conn.close()


def read_sqlite_value(path: Path) -> str:
    conn = sqlite3.connect(path)
    try:
        row = conn.execute("SELECT value FROM probe").fetchone()
        return str(row[0])
    finally:
        conn.close()


def main() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        sqlite_path = root / "runtime" / "sqlite" / "app.db"
        qdrant_path = root / "runtime" / "qdrant"
        backup_root = root / "backups"

        write_sqlite_value(sqlite_path, "before")
        qdrant_path.mkdir(parents=True)
        (qdrant_path / "meta.json").write_text('{"status":"before"}', encoding="utf-8")
        (qdrant_path / ".lock").write_text("do not back up", encoding="utf-8")

        backup = backup_runtime_state(
            sqlite_path=sqlite_path,
            qdrant_path=qdrant_path,
            backup_root=backup_root,
        )
        inspected = inspect_runtime_backup(backup["backup_path"])
        assert inspected["artifacts"]["sqlite"]["exists"] is True
        assert inspected["artifacts"]["qdrant"]["exists"] is True
        assert not (Path(backup["backup_path"]) / "qdrant" / ".lock").exists()

        write_sqlite_value(sqlite_path, "after")
        (qdrant_path / "meta.json").write_text('{"status":"after"}', encoding="utf-8")

        restored = restore_runtime_state(
            backup_path=backup["backup_path"],
            sqlite_path=sqlite_path,
            qdrant_path=qdrant_path,
            force=True,
        )

        assert restored["artifacts"]["sqlite"]["restored"] is True
        assert restored["artifacts"]["qdrant"]["restored"] is True
        assert read_sqlite_value(sqlite_path) == "before"
        assert (qdrant_path / "meta.json").read_text(encoding="utf-8") == '{"status":"before"}'
        assert restored["artifacts"]["sqlite"]["moved_existing_to"]
        assert restored["artifacts"]["qdrant"]["moved_existing_to"]

        backup_runtime_state(
            sqlite_path=sqlite_path,
            qdrant_path=qdrant_path,
            backup_root=backup_root,
        )
        backup_runtime_state(
            sqlite_path=sqlite_path,
            qdrant_path=qdrant_path,
            backup_root=backup_root,
        )
        backups = list_runtime_backups(backup_root)
        assert len(backups) == 3
        assert all(backup["valid"] is True for backup in backups)

        dry_run = prune_runtime_backups(backup_root=backup_root, keep=1, dry_run=True)
        assert dry_run["dry_run"] is True
        assert dry_run["kept_count"] == 1
        assert dry_run["would_delete_count"] == 2
        assert len(list_runtime_backups(backup_root)) == 3

        pruned = prune_runtime_backups(backup_root=backup_root, keep=1, dry_run=False)
        assert pruned["dry_run"] is False
        assert pruned["kept_count"] == 1
        assert pruned["deleted_count"] == 2
        remaining = list_runtime_backups(backup_root)
        assert len(remaining) == 1
        assert Path(remaining[0]["backup_path"]).exists()

    print("Runtime backup smoke test passed.")


if __name__ == "__main__":
    main()
