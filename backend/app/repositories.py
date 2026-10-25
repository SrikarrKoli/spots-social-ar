from __future__ import annotations

from datetime import UTC, datetime

from .database import Database
from .models import ConversationPreview, ObjectSummary, Post, Profile, ThreadResponse


class NotFoundError(Exception):
    pass


class InvalidReplyError(Exception):
    pass


def _profile(row: object) -> Profile:
    return Profile(
        id=row["author_id"],
        display_name=row["display_name"],
        initials=row["initials"],
        color=row["color"],
    )


_OBJECT_COLUMNS = "id, identity_key, identity_kind, title, description"


class Repository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def profiles(self) -> list[Profile]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT id, display_name, initials, color FROM users "
                "ORDER BY CASE id WHEN 'guest' THEN 1 ELSE 0 END, display_name"
            ).fetchall()
        return [Profile.model_validate(dict(row)) for row in rows]

    def object_by_identity(self, identity_key: str) -> ObjectSummary | None:
        with self.database.connect() as connection:
            row = connection.execute(
                f"SELECT {_OBJECT_COLUMNS} FROM objects "
                "WHERE identity_key = ? OR CAST(marker_id AS TEXT) = ?",
                (identity_key, identity_key),
            ).fetchone()
        return ObjectSummary.model_validate(dict(row)) if row else None

    # Backwards-compatible alias for the legacy ArUco fixture path.
    def object_by_marker(self, marker_id: int) -> ObjectSummary | None:
        return self.object_by_identity(str(marker_id))

    def object_references(
        self, *, max_per_identity: int | None = None
    ) -> list[tuple[str, str]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT o.identity_key, f.reference_path
                FROM object_fingerprints f
                JOIN objects o ON o.id = f.object_id
                WHERE f.reference_path IS NOT NULL AND o.identity_key IS NOT NULL
                ORDER BY o.id, f.id
                """
            ).fetchall()
        references = [
            (row["identity_key"], row["reference_path"]) for row in rows
        ]
        if max_per_identity is None:
            return references

        grouped: dict[str, tuple[list[str], list[str]]] = {}
        for identity_key, path in references:
            deliberate, banked = grouped.setdefault(identity_key, ([], []))
            (banked if "-banked-" in path else deliberate).append(path)

        selected: list[tuple[str, str]] = []
        for identity_key, (deliberate, banked) in grouped.items():
            paths = (deliberate + banked)[:max_per_identity]
            selected.extend((identity_key, path) for path in paths)
        return selected

    def recognition_context(
        self, identity_keys: list[str]
    ) -> dict[str, tuple[ObjectSummary, ConversationPreview | None]]:
        """Resolve detection labels and previews in one bounded query."""
        if not identity_keys:
            return {}
        placeholders = ",".join("?" for _ in identity_keys)
        with self.database.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT o.identity_key, o.id, o.identity_kind, o.title,
                       o.description, p.body AS preview_body,
                       u.display_name AS preview_author,
                       COALESCE((
                           SELECT COUNT(*) FROM posts r
                           WHERE r.parent_post_id = p.id
                       ), 0) AS reply_count
                FROM objects o
                LEFT JOIN posts p ON p.id = (
                    SELECT candidate.id FROM posts candidate
                    WHERE candidate.object_id = o.id
                      AND candidate.parent_post_id IS NULL
                    ORDER BY candidate.created_at DESC, candidate.id DESC
                    LIMIT 1
                )
                LEFT JOIN users u ON u.id = p.author_id
                WHERE o.identity_key IN ({placeholders})
                """,
                identity_keys,
            ).fetchall()

        context: dict[str, tuple[ObjectSummary, ConversationPreview | None]] = {}
        for row in rows:
            record = ObjectSummary(
                id=row["id"],
                identity_key=row["identity_key"],
                identity_kind=row["identity_kind"],
                title=row["title"],
                description=row["description"],
            )
            preview = (
                ConversationPreview(
                    author_name=row["preview_author"],
                    body=row["preview_body"],
                    reply_count=int(row["reply_count"]),
                )
                if row["preview_body"] is not None
                else None
            )
            context[record.identity_key] = (record, preview)
        return context

    def enroll_object(
        self,
        *,
        object_id: str,
        title: str,
        description: str | None,
        reference_path: str,
        extra_reference_paths: tuple[str, ...] = (),
    ) -> ObjectSummary:
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO objects(
                    id, identity_key, identity_kind, reference_path, title, description
                ) VALUES (?, ?, 'instance', ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    title = excluded.title,
                    description = excluded.description,
                    reference_path = excluded.reference_path
                """,
                (object_id, object_id, reference_path, title, description),
            )
            for path in (reference_path, *extra_reference_paths):
                connection.execute(
                    """
                    INSERT INTO object_fingerprints(object_id, kind, reference_path)
                    SELECT ?, 'reference-image', ?
                    WHERE NOT EXISTS (
                        SELECT 1 FROM object_fingerprints
                        WHERE object_id = ? AND reference_path = ?
                    )
                    """,
                    (object_id, path, object_id, path),
                )
            row = connection.execute(
                f"SELECT {_OBJECT_COLUMNS} FROM objects WHERE id = ?",
                (object_id,),
            ).fetchone()
        return ObjectSummary.model_validate(dict(row))

    def object_reference_paths(self, object_id: str) -> list[str]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT reference_path FROM object_fingerprints "
                "WHERE object_id = ? AND reference_path IS NOT NULL ORDER BY id",
                (object_id,),
            ).fetchall()
        return [row["reference_path"] for row in rows]

    def post_count(self, object_id: str) -> int:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS n FROM posts WHERE object_id = ?", (object_id,)
            ).fetchone()
        return int(row["n"])

    def delete_object(self, object_id: str) -> None:
        with self.database.connect() as connection:
            connection.execute(
                "DELETE FROM object_fingerprints WHERE object_id = ?", (object_id,)
            )
            connection.execute("DELETE FROM objects WHERE id = ?", (object_id,))

    def add_reference_path(self, object_id: str, reference_path: str) -> None:
        """Record an extra enrolled view (e.g. a banked new angle)."""
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO object_fingerprints(object_id, kind, reference_path)
                SELECT ?, 'reference-image', ?
                WHERE NOT EXISTS (
                    SELECT 1 FROM object_fingerprints
                    WHERE object_id = ? AND reference_path = ?
                )
                """,
                (object_id, reference_path, object_id, reference_path),
            )

    def objects(self) -> list[ObjectSummary]:
        with self.database.connect() as connection:
            rows = connection.execute(
                f"SELECT {_OBJECT_COLUMNS} FROM objects ORDER BY title"
            ).fetchall()
        return [ObjectSummary.model_validate(dict(row)) for row in rows]

    def object_by_id(self, object_id: str) -> ObjectSummary | None:
        with self.database.connect() as connection:
            row = connection.execute(
                f"SELECT {_OBJECT_COLUMNS} FROM objects WHERE id = ?",
                (object_id,),
            ).fetchone()
        return ObjectSummary.model_validate(dict(row)) if row else None

    def thread(self, object_id: str) -> ThreadResponse:
        object_record = self.object_by_id(object_id)
        if object_record is None:
            raise NotFoundError("Object not found")

        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT p.id, p.object_id, p.body, p.created_at, p.parent_post_id,
                       p.author_id, u.display_name, u.initials, u.color
                FROM posts p JOIN users u ON u.id = p.author_id
                WHERE p.object_id = ?
                ORDER BY p.created_at, p.id
                """,
                (object_id,),
            ).fetchall()

        posts_by_id: dict[int, Post] = {}
        roots: list[Post] = []
        latest: datetime | None = None
        for row in rows:
            post = Post(
                id=row["id"],
                object_id=row["object_id"],
                author=_profile(row),
                body=row["body"],
                created_at=datetime.fromisoformat(row["created_at"]),
                parent_post_id=row["parent_post_id"],
            )
            posts_by_id[post.id] = post
            latest = post.created_at
            if post.parent_post_id is None:
                roots.append(post)
            elif post.parent_post_id in posts_by_id:
                posts_by_id[post.parent_post_id].replies.append(post)

        return ThreadResponse(object=object_record, posts=roots, updated_at=latest)

    def create_post(
        self,
        *,
        object_id: str,
        author_id: str,
        body: str,
        parent_post_id: int | None,
        client_request_id: str,
    ) -> Post:
        created_at = datetime.now(UTC).isoformat()
        with self.database.connect() as connection:
            if connection.execute(
                "SELECT 1 FROM objects WHERE id = ?", (object_id,)
            ).fetchone() is None:
                raise NotFoundError("Object not found")
            if connection.execute(
                "SELECT 1 FROM users WHERE id = ?", (author_id,)
            ).fetchone() is None:
                raise NotFoundError("Profile not found")

            existing = connection.execute(
                """
                SELECT id, object_id, author_id, body, parent_post_id
                FROM posts WHERE client_request_id = ?
                """,
                (client_request_id,),
            ).fetchone()
            if existing is not None:
                if (
                    existing["object_id"] != object_id
                    or existing["author_id"] != author_id
                    or existing["body"] != body
                    or existing["parent_post_id"] != parent_post_id
                ):
                    raise InvalidReplyError(
                        "Idempotency key was already used for a different message"
                    )
                post_id = int(existing["id"])
            else:
                if parent_post_id is not None:
                    parent = connection.execute(
                        "SELECT object_id, parent_post_id FROM posts WHERE id = ?",
                        (parent_post_id,),
                    ).fetchone()
                    if parent is None:
                        raise NotFoundError("Reply target not found")
                    if parent["object_id"] != object_id:
                        raise InvalidReplyError(
                            "Reply target belongs to a different object"
                        )
                    if parent["parent_post_id"] is not None:
                        raise InvalidReplyError("Replies can only target top-level posts")

                cursor = connection.execute(
                    """
                    INSERT INTO posts(
                        object_id, author_id, body, created_at,
                        parent_post_id, client_request_id
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        object_id,
                        author_id,
                        body,
                        created_at,
                        parent_post_id,
                        client_request_id,
                    ),
                )
                post_id = int(cursor.lastrowid)

            row = connection.execute(
                """
                SELECT p.id, p.object_id, p.body, p.created_at, p.parent_post_id,
                       p.author_id, u.display_name, u.initials, u.color
                FROM posts p JOIN users u ON u.id = p.author_id
                WHERE p.id = ?
                """,
                (post_id,),
            ).fetchone()

        return Post(
            id=row["id"],
            object_id=row["object_id"],
            author=_profile(row),
            body=row["body"],
            created_at=datetime.fromisoformat(row["created_at"]),
            parent_post_id=row["parent_post_id"],
        )
