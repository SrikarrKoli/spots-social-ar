from __future__ import annotations

import argparse
import shutil
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from backend.app.config import ROOT, Settings
from backend.app.database import Database
from backend.app.repositories import Repository


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Report or prune surplus auto-banked recognition views"
    )
    parser.add_argument(
        "--max-per-identity",
        type=int,
        help="Active physical views to retain (defaults to app configuration)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Back up the database and delete reported banked rows/files",
    )
    arguments = parser.parse_args()
    settings = Settings.from_env()
    limit = arguments.max_per_identity or settings.max_reference_files_per_identity
    if limit < 1:
        raise SystemExit("--max-per-identity must be positive")

    database = Database(settings.database_path)
    repository = Repository(database)
    retained = set(repository.object_references(max_per_identity=limit))
    with database.connect() as connection:
        rows = connection.execute(
            """
            SELECT f.id, o.identity_key, f.reference_path
            FROM object_fingerprints f
            JOIN objects o ON o.id = f.object_id
            WHERE f.reference_path IS NOT NULL
            ORDER BY o.id, f.id
            """
        ).fetchall()

    surplus: list[tuple[int, str, Path]] = []
    enrolled_root = settings.enrolled_dir.resolve()
    for row in rows:
        key = (row["identity_key"], row["reference_path"])
        if key in retained or "-banked-" not in row["reference_path"]:
            continue
        raw = Path(row["reference_path"])
        path = (raw if raw.is_absolute() else ROOT / raw).resolve()
        if enrolled_root not in path.parents:
            raise SystemExit(f"Refusing ambiguous banked path outside enrolled dir: {path}")
        surplus.append((int(row["id"]), row["identity_key"], path))

    reclaimed = sum(path.stat().st_size for _, _, path in surplus if path.exists())
    print(
        f"surplus_banked_views={len(surplus)} "
        f"estimated_reclaimed_bytes={reclaimed} apply={arguments.apply}"
    )
    for _, identity, path in surplus:
        print(f"{identity}\t{path}")
    if not arguments.apply or not surplus:
        return 0

    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    backup = settings.database_path.with_name(
        f"{settings.database_path.name}.backup-{timestamp}"
    )
    shutil.copy2(settings.database_path, backup)
    ids = [row_id for row_id, _, _ in surplus]
    placeholders = ",".join("?" for _ in ids)
    connection = sqlite3.connect(settings.database_path)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(
            f"DELETE FROM object_fingerprints WHERE id IN ({placeholders})", ids
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
    for _, _, path in surplus:
        path.unlink(missing_ok=True)
    print(f"backup={backup}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
