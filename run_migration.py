"""
run_migration.py
----------------
Run the Supabase migration directly via psycopg2.

Usage:
    python run_migration.py <DB_PASSWORD>
    # or set SUPABASE_DB_PASSWORD in .env and run with no args
"""
import os
import sys
import psycopg2
from dotenv import load_dotenv

load_dotenv()

_SQL_FILE = os.path.join(os.path.dirname(__file__), "data", "migrations", "002_features.sql")
_PROJECT_REF = "xnskpnrqqdeapwkvniid"


def run(db_password: str) -> None:
    print(f"Connecting to Supabase project {_PROJECT_REF} ...")

    with open(_SQL_FILE, "r") as f:
        sql = f.read()

    # Try direct connection first, then pooler
    hosts = [
        (f"db.{_PROJECT_REF}.supabase.co", 5432, "postgres"),
        ("aws-0-us-east-1.pooler.supabase.com", 5432, f"postgres.{_PROJECT_REF}"),
        ("aws-0-us-west-1.pooler.supabase.com", 5432, f"postgres.{_PROJECT_REF}"),
        ("aws-0-eu-west-1.pooler.supabase.com", 5432, f"postgres.{_PROJECT_REF}"),
    ]

    conn = None
    for host, port, user in hosts:
        try:
            print(f"  Trying {host}:{port} ...")
            conn = psycopg2.connect(
                host=host, port=port, database="postgres",
                user=user, password=db_password, sslmode="require",
                connect_timeout=10,
            )
            print(f"  Connected via {host}")
            break
        except Exception as e:
            print(f"  Failed: {e}")

    if conn is None:
        print("\nCould not connect to any host. Check your password and network.")
        sys.exit(1)

    try:
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute(sql)
        print("\nMigration completed successfully.")
        print("Tables created/updated: accounts, signals (extended), trades (extended),")
        print("                        improvement_history, autonomous_log")
    except Exception as e:
        print(f"\nMigration failed: {e}")
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    password = (
        sys.argv[1] if len(sys.argv) > 1
        else os.getenv("SUPABASE_DB_PASSWORD", "")
    )
    if not password:
        print("Usage: python run_migration.py <DB_PASSWORD>")
        print("   or: set SUPABASE_DB_PASSWORD in .env")
        sys.exit(1)
    run(password)
