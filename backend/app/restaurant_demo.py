"""Optional, isolated restaurant fixtures for the Instagram presentation."""
from datetime import datetime, timezone
from .database import Database

MENU = (
    ("chicken-tikka", "Chicken Tikka Masala", "Get this with garlic naan. Smoky, not too sweet."),
    ("madras-curry", "Madras Chicken Curry", "Ask for medium and get rice and naan with it."),
    ("kabab", "Beef Chapli Kabab Sizzler", "Comes out sizzling. Order one for the table."),
    ("pani-puri", "Pani Puri", "Eat each one in one bite so the water doesn't spill."),
)

def seed_restaurant_demo(database: Database) -> None:
    with database.connect() as connection:
        for slug, title, body in MENU:
            object_id = f"demo-menu-{slug}"
            connection.execute(
                "INSERT INTO objects(id, identity_key, identity_kind, title, description) "
                "VALUES (?, ?, 'demo', ?, 'Illustrative restaurant scene') ON CONFLICT DO NOTHING",
                (object_id, object_id, title),
            )
            connection.execute(
                "INSERT INTO posts(object_id, author_id, body, created_at, seed_key) "
                "VALUES (?, 'maya', ?, ?, ?) ON CONFLICT DO NOTHING",
                (object_id, f"[Demo] {body}", datetime.now(timezone.utc).isoformat(), f"instagram-{slug}"),
            )
