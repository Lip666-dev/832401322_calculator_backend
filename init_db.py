#!/usr/bin/env python3
"""Create (or reset) the SQLite database used by the calculator backend.

Usage::

    python init_db.py                 # create data/calculator.db and its schema
    python init_db.py --reset         # delete all rows, then recreate the schema
    python init_db.py --db other.db   # use another database file

The API server also creates the schema automatically on startup, so this script
is only needed when the database has to be prepared or cleaned explicitly.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.config import Settings
from src.model.database import Database


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Initialise the calculator database.")
    parser.add_argument("--db", dest="db_path", help="path of the SQLite file")
    parser.add_argument(
        "--reset", action="store_true", help="delete every stored calculation first"
    )
    args = parser.parse_args(argv)

    settings = Settings.from_env()
    if args.db_path:
        settings.db_path = Path(args.db_path)

    database = Database(settings.resolved_db_path())
    print(f"Database file : {database.path}")

    if args.reset and database.path.exists():
        database.initialize()
        with database.connection() as connection:
            removed = connection.execute("DELETE FROM calculation_history").rowcount
        print(f"Removed       : {removed} calculation record(s)")

    database.initialize()

    with database.connection() as connection:
        columns = connection.execute("PRAGMA table_info(calculation_history)").fetchall()
        indexes = connection.execute("PRAGMA index_list(calculation_history)").fetchall()

    print("Table         : calculation_history")
    for column in columns:
        primary = " PRIMARY KEY" if column["pk"] else ""
        print(f"  - {column['name']:<13} {column['type']}{primary}")
    print(f"Indexes       : {', '.join(index['name'] for index in indexes)}")
    print("Ready. Start the API with: python run.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
