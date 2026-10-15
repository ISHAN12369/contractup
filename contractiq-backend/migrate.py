"""Apply the idempotent schema with deployment-admin credentials before starting APIs."""
from pathlib import Path

import psycopg
from dotenv import load_dotenv

from config import Settings


def main() -> None:
    load_dotenv()
    settings = Settings.from_env()
    with psycopg.connect(settings.database_url, connect_timeout=5) as conn:
        conn.execute("SELECT pg_advisory_xact_lock(72143588)")
        conn.execute((Path(__file__).parent / "migrations/001_production.sql").read_text(encoding="utf-8"))
    print("Production schema is ready.")


if __name__ == "__main__":
    main()
