"""
FLIPUS v1.2 — Migrasi SQLite ke PostgreSQL.

Strategi:
1. Dump SQLite schema + data pakai SQL statements
2. Connect ke PostgreSQL, create schema
3. Insert data per table

Jalankan di Mac:
    /Users/jerrymauri/Flipus/.venv/bin/python3 -m storage.scripts.migrate_sqlite_to_postgres

Environment:
    PG_HOST=localhost
    PG_PORT=5432
    PG_USER=flipus
    PG_PASSWORD=flipus
    PG_DATABASE=flipus
"""

import os
import sys
import sqlite3
from pathlib import Path
from urllib.parse import urlparse

try:
    import psycopg2
    from psycopg2.extras import execute_values
except ImportError:
    print("Install psycopg2-binary dulu: pip install psycopg2-binary --break-system-packages")
    sys.exit(1)


def get_sqlite_path() -> Path:
    """Get SQLite path dari DATABASE_URL_LOCAL."""
    url = os.environ.get("DATABASE_URL_LOCAL", "sqlite:///./flipus_local.db")
    if url.startswith("sqlite:///"):
        p = url[10:]
    elif url.startswith("sqlite://"):
        p = url[9:]
    else:
        raise ValueError(f"Bukan SQLite URL: {url}")
    return Path(p) if Path(p).is_absolute() else Path.cwd() / p


def get_pg_config():
    return {
        "host": os.environ.get("PG_HOST", "localhost"),
        "port": int(os.environ.get("PG_PORT", "5432")),
        "user": os.environ.get("PG_USER", "flipus"),
        "password": os.environ.get("PG_PASSWORD", "flipus"),
        "database": os.environ.get("PG_DATABASE", "flipus"),
    }


def get_sqlite_tables(conn):
    """List semua table di SQLite."""
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
    return [row[0] for row in cur.fetchall()]


def get_sqlite_create_statements(conn):
    """Get CREATE TABLE statements dari SQLite."""
    cur = conn.cursor()
    cur.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
    return [row[0] for row in cur.fetchall()]


def convert_sqlite_to_pg(sqlite_sql: str) -> str:
    """Convert SQLite CREATE TABLE ke PostgreSQL compatible."""
    s = sqlite_sql

    # SQLite types → PostgreSQL types
    s = s.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")
    s = s.replace("INTEGER PRIMARY KEY", "SERIAL PRIMARY KEY")
    s = s.replace("BIGINT", "BIGINT")  # sama
    s = s.replace("DATETIME", "TIMESTAMP")
    s = s.replace("BOOLEAN", "BOOLEAN")

    # SQLite-specific syntax
    s = s.replace("VARCHAR", "VARCHAR")  # sama
    s = s.replace("TEXT", "TEXT")

    return s


def get_sqlite_data(conn, table: str):
    """Get all rows dari SQLite table."""
    cur = conn.cursor()
    cur.execute(f'SELECT * FROM "{table}"')
    cols = [d[0] for d in cur.description]
    return cols, cur.fetchall()


def migrate_table(pg_conn, table: str, sqlite_cols, sqlite_rows):
    """Insert data ke PostgreSQL."""
    if not sqlite_rows:
        print(f"  → {table}: 0 rows, skip")
        return 0

    cur = pg_conn.cursor()

    # Build INSERT
    cols_str = ", ".join(f'"{c}"' for c in sqlite_cols)
    placeholders = ", ".join(["%s"] * len(sqlite_cols))
    insert_sql = f'INSERT INTO "{table}" ({cols_str}) VALUES ({placeholders}) ON CONFLICT DO NOTHING'

    inserted = 0
    for row in sqlite_rows:
        try:
            cur.execute(insert_sql, row)
            inserted += 1
        except Exception as e:
            print(f"    Warning: skip row in {table}: {e}")

    pg_conn.commit()
    print(f"  → {table}: {inserted}/{len(sqlite_rows)} rows inserted")
    return inserted


def main():
    sqlite_path = get_sqlite_path()
    if not sqlite_path.exists():
        print(f"SQLite DB not found: {sqlite_path}")
        sys.exit(1)

    print(f"Source: {sqlite_path}")
    print(f"Target: {get_pg_config()}")

    # Connect ke SQLite
    sqlite_conn = sqlite3.connect(str(sqlite_path))
    sqlite_conn.row_factory = None

    # Get schema
    tables = get_sqlite_tables(sqlite_conn)
    creates = get_sqlite_create_statements(sqlite_conn)

    print(f"\nTables: {len(tables)}")
    for t in tables:
        print(f"  - {t}")

    # Connect ke PostgreSQL
    try:
        pg_conn = psycopg2.connect(**get_pg_config())
    except Exception as e:
        print(f"\nPostgreSQL connection gagal: {e}")
        print("Pastikan Postgres running & DATABASE_URL benar.")
        sys.exit(1)

    # 1) Create schema
    print("\n=== Creating schema ===")
    pg_cur = pg_conn.cursor()
    pg_cur.execute("CREATE SCHEMA IF NOT EXISTS public")

    for create_sql in creates:
        pg_sql = convert_sqlite_to_pg(create_sql)
        try:
            pg_cur.execute(pg_sql)
            print(f"  ✓ Created")
        except Exception as e:
            print(f"  ✗ Error: {e}")

    pg_conn.commit()

    # 2) Insert data
    print("\n=== Inserting data ===")
    total = 0
    for table in tables:
        try:
            cols, rows = get_sqlite_data(sqlite_conn, table)
            inserted = migrate_table(pg_conn, table, cols, rows)
            total += inserted
        except Exception as e:
            print(f"  ✗ {table}: {e}")

    sqlite_conn.close()
    pg_conn.close()

    print(f"\n✓ Migration selesai: {total} rows total")
    print(f"\nNext steps:")
    print(f"  1. Update DATABASE_URL_LOCAL di .env ke PostgreSQL")
    print(f"  2. Restart backend")
    print(f"  3. Verify data via Swagger /docs")


if __name__ == "__main__":
    main()