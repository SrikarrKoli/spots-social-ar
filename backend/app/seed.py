from __future__ import annotations

import argparse

from .config import Settings
from .database import Database, seed_demo


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the Locus demo database")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete all posts and restore the known demo state",
    )
    args = parser.parse_args()
    settings = Settings.from_env()
    seed_demo(Database(settings.database_path), reset=args.reset)
    action = "Reset" if args.reset else "Seeded"
    print(f"{action} demo database at {settings.database_path}")


if __name__ == "__main__":
    main()
