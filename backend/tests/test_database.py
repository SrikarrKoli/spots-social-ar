from __future__ import annotations

import sqlite3
from pathlib import Path

from backend.app.database import Database, seed_demo
from backend.app.repositories import Repository

OLD_SCHEMA = """
CREATE TABLE users (
    id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL UNIQUE,
    initials TEXT NOT NULL,
    color TEXT NOT NULL
);
CREATE TABLE objects (
    id TEXT PRIMARY KEY,
    marker_id INTEGER NOT NULL UNIQUE,
    title TEXT NOT NULL,
    description TEXT
);
CREATE TABLE posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    object_id TEXT NOT NULL REFERENCES objects(id) ON DELETE CASCADE,
    author_id TEXT NOT NULL REFERENCES users(id),
    body TEXT NOT NULL,
    created_at TEXT NOT NULL,
    parent_post_id INTEGER REFERENCES posts(id) ON DELETE CASCADE,
    client_request_id TEXT UNIQUE,
    seed_key TEXT UNIQUE
);
"""


def _make_old_db(path: Path) -> None:
    connection = sqlite3.connect(path)
    connection.executescript(OLD_SCHEMA)
    connection.execute(
        "INSERT INTO objects(id, marker_id, title) VALUES ('legacy', 99, 'Legacy')"
    )
    connection.commit()
    connection.close()


def test_old_marker_schema_migrates_and_accepts_markerless_enroll(tmp_path: Path):
    path = tmp_path / "old.db"
    _make_old_db(path)

    database = Database(path)
    seed_demo(database)
    seed_demo(database)  # migration + seed must be idempotent

    repository = Repository(database)
    created = repository.enroll_object(
        object_id="blue-mug-abc123",
        title="Blue mug",
        description=None,
        reference_path="data/enrolled/blue-mug-abc123.png",
    )
    assert created.identity_key == "blue-mug-abc123"

    legacy = repository.object_by_id("legacy")
    assert legacy is not None
    assert legacy.identity_key == "legacy"
    # Seeded threads still work after the table rebuild.
    assert repository.thread("concert-poster").posts[0].body == (
        "Anyone want to go Friday?"
    )
