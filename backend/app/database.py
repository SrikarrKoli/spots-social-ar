from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL UNIQUE,
    initials TEXT NOT NULL,
    color TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS objects (
    id TEXT PRIMARY KEY,
    marker_id INTEGER NOT NULL UNIQUE,
    title TEXT NOT NULL,
    description TEXT
);

CREATE TABLE IF NOT EXISTS posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    object_id TEXT NOT NULL REFERENCES objects(id) ON DELETE CASCADE,
    author_id TEXT NOT NULL REFERENCES users(id),
    body TEXT NOT NULL CHECK(length(body) BETWEEN 1 AND 500),
    created_at TEXT NOT NULL,
    parent_post_id INTEGER REFERENCES posts(id) ON DELETE CASCADE,
    client_request_id TEXT UNIQUE,
    seed_key TEXT UNIQUE
);

CREATE INDEX IF NOT EXISTS posts_object_created
    ON posts(object_id, created_at, id);
CREATE INDEX IF NOT EXISTS posts_parent
    ON posts(parent_post_id);
"""


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.executescript(SCHEMA)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA busy_timeout = 5000")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def reset(self) -> None:
        with self.connect() as connection:
            connection.execute("DELETE FROM posts")
            connection.execute("DELETE FROM objects")
            connection.execute("DELETE FROM users")
            connection.execute("DELETE FROM sqlite_sequence WHERE name = 'posts'")


USERS = (
    ("maya", "Vishal Rajkumar", "VR", "#E76F51"),
    ("theo", "Aneesh Dhulipalla", "AD", "#457B9D"),
)

OBJECTS = (
    (
        "concert-poster",
        7,
        "Chicken Tikka Masala",
        "Grilled boneless chicken in an onion and tomato-cream curry.",
    ),
    (
        "favorite-book",
        23,
        "Madras Chicken Curry",
        "Charcoal-grilled chicken, carrots, and potatoes in a Madras curry.",
    ),
    (
        "mushroom-bucatini",
        31,
        "Beef Chapli Kabab Sizzler",
        "Distinctively spiced, handmade local beef kabab.",
    ),
    (
        "pani-puri",
        12,
        "Pani Puri",
        "Crispy puris filled with potatoes, chickpeas, and chutneys.",
    ),
)

SEED_POSTS = (
    (
        "concert-question",
        "concert-poster",
        "maya",
        "Get this with garlic naan. Smoky, not too sweet.",
        "2026-10-24T18:00:00+00:00",
        None,
    ),
    (
        "book-recommendation",
        "favorite-book",
        "maya",
        "Madras curry has a slow-building heat. Ask for medium and get rice and naan with it.",
        "2026-10-24T18:05:00+00:00",
        None,
    ),
    (
        "bucatini-recommendation",
        "mushroom-bucatini",
        "maya",
        "Best thing on the menu. Comes out sizzling, so order one for the table.",
        "2026-10-24T18:07:00+00:00",
        None,
    ),
    (
        "pani-puri-recommendation",
        "pani-puri",
        "maya",
        "The pani puri here is so good. Eat each one in one bite so the water doesn't spill.",
        "2026-10-24T18:03:00+00:00",
        None,
    ),
)


def seed_demo(database: Database, *, reset: bool = False) -> None:
    database.initialize()
    if reset:
        database.reset()

    with database.connect() as connection:
        active_seed_keys = tuple(post[0] for post in SEED_POSTS)
        placeholders = ", ".join("?" for _ in active_seed_keys)
        connection.execute(
            f"DELETE FROM posts WHERE seed_key IS NOT NULL AND seed_key NOT IN ({placeholders})",
            active_seed_keys,
        )
        connection.execute(
            "DELETE FROM posts WHERE client_request_id = ?",
            ("acceptance-jordan-ramen-reply-v1",),
        )
        connection.executemany(
            """
            INSERT INTO users(id, display_name, initials, color)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                display_name = excluded.display_name,
                initials = excluded.initials,
                color = excluded.color
            """,
            USERS,
        )
        connection.executemany(
            """
            INSERT INTO objects(id, marker_id, title, description)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                marker_id = excluded.marker_id,
                title = excluded.title,
                description = excluded.description
            """,
            OBJECTS,
        )

        seed_ids: dict[str, int] = {}
        for seed_key, object_id, author_id, body, created_at, parent_seed in SEED_POSTS:
            parent_id = seed_ids.get(parent_seed) if parent_seed else None
            connection.execute(
                """
                INSERT INTO posts(
                    object_id, author_id, body, created_at, parent_post_id, seed_key
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(seed_key) DO UPDATE SET
                    object_id = excluded.object_id,
                    author_id = excluded.author_id,
                    body = excluded.body,
                    created_at = excluded.created_at,
                    parent_post_id = excluded.parent_post_id
                """,
                (object_id, author_id, body, created_at, parent_id, seed_key),
            )
            row = connection.execute(
                "SELECT id FROM posts WHERE seed_key = ?", (seed_key,)
            ).fetchone()
            if row is not None:
                seed_ids[seed_key] = int(row["id"])

        connection.execute(
            """
            DELETE FROM users
            WHERE id NOT IN ('maya', 'theo')
              AND NOT EXISTS (SELECT 1 FROM posts WHERE posts.author_id = users.id)
            """
        )
