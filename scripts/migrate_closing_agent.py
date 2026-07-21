"""Idempotent database migration for the closing-agent feature.

Adds new columns to the existing `orders` table and creates new tables
(`closing_sessions`, `webhook_events`). Safe to run multiple times.

Usage:
    1. Stop the application
    2. python scripts/migrate_closing_agent.py
    3. Review output — verify all expected columns are present
    4. Start the application

    Backup is created automatically at data/bheem.db.backup_<timestamp>
    To rollback: copy the backup file back to data/bheem.db
"""

import os
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

# Resolve project root (one level up from scripts/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "data" / "bheem.db"


def backup_database(db_path: Path) -> Path:
    """Create a timestamped backup of the database."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = db_path.parent / f"{db_path.stem}.db.backup_{timestamp}"
    shutil.copy2(db_path, backup_path)
    print(f"✅ Backup created: {backup_path}")
    return backup_path


def get_existing_columns(conn: sqlite3.Connection, table: str) -> set:
    """Get the set of column names in an existing table."""
    cursor = conn.execute(f"PRAGMA table_info({table})")
    return {row[1] for row in cursor.fetchall()}


def add_column_if_missing(conn: sqlite3.Connection, table: str, col_name: str,
                           col_type: str, existing_cols: set) -> str:
    """Add a column to a table if it doesn't already exist. Returns status."""
    if col_name in existing_cols:
        return "already exists"
    try:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type}")
        return "added"
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e).lower():
            return "already exists (caught)"
        raise


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    """Check if a table exists in the database."""
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
    )
    return cursor.fetchone() is not None


def migrate_orders_table(conn: sqlite3.Connection) -> None:
    """Add new columns to the existing orders table."""
    print("\n── Migrating orders table ──")

    if not table_exists(conn, "orders"):
        print("  ⚠️  orders table does not exist — it will be created by the app on startup")
        return

    existing = get_existing_columns(conn, "orders")
    print(f"  Existing columns: {sorted(existing)}")

    # New columns to add
    new_columns = [
        ("user_id", "INTEGER REFERENCES users(id)"),
        ("course_id", "VARCHAR(100)"),
        ("course_name", "VARCHAR(255)"),
        ("amount", "INTEGER"),
        ("currency", "VARCHAR(10) DEFAULT 'INR'"),
        ("internal_order_id", "VARCHAR(100)"),
        ("razorpay_payment_link_id", "VARCHAR(255)"),
        ("razorpay_payment_url", "VARCHAR(1024)"),
        ("razorpay_payment_id", "VARCHAR(255)"),
        ("paid_at", "DATETIME"),
    ]

    for col_name, col_type in new_columns:
        status = add_column_if_missing(conn, "orders", col_name, col_type, existing)
        print(f"  {col_name}: {status}")

    # Handle payment_link_id → razorpay_payment_link_id data copy
    if "payment_link_id" in existing and "razorpay_payment_link_id" in (
        existing | {c[0] for c in new_columns}
    ):
        # Copy data from old column to new column where new is NULL
        try:
            conn.execute("""
                UPDATE orders
                SET razorpay_payment_link_id = payment_link_id
                WHERE razorpay_payment_link_id IS NULL
                  AND payment_link_id IS NOT NULL
            """)
            cursor = conn.execute(
                "SELECT COUNT(*) FROM orders WHERE razorpay_payment_link_id IS NOT NULL"
            )
            count = cursor.fetchone()[0]
            print(f"  payment_link_id → razorpay_payment_link_id: {count} rows synced")
        except sqlite3.OperationalError as e:
            print(f"  payment_link_id data copy: skipped ({e})")

    conn.commit()

    # Verify
    final_cols = get_existing_columns(conn, "orders")
    print(f"  Final columns: {sorted(final_cols)}")


def create_closing_sessions_table(conn: sqlite3.Connection) -> None:
    """Create the closing_sessions table if it doesn't exist."""
    print("\n── Creating closing_sessions table ──")

    if table_exists(conn, "closing_sessions"):
        print("  Already exists — skipping")
        return

    conn.execute("""
        CREATE TABLE closing_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER NOT NULL UNIQUE REFERENCES conversations(id),
            state VARCHAR(50) NOT NULL DEFAULT 'GREETING',
            selected_course_id VARCHAR(100),
            active_order_id INTEGER REFERENCES orders(id),
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    print("  ✅ Created")


def create_webhook_events_table(conn: sqlite3.Connection) -> None:
    """Create the webhook_events table if it doesn't exist."""
    print("\n── Creating webhook_events table ──")

    if table_exists(conn, "webhook_events"):
        print("  Already exists — skipping")
        return

    conn.execute("""
        CREATE TABLE webhook_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider VARCHAR(50) NOT NULL,
            external_event_id VARCHAR(255) NOT NULL UNIQUE,
            event_type VARCHAR(100),
            payload_json TEXT,
            status VARCHAR(50) DEFAULT 'received',
            received_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            processed_at DATETIME
        )
    """)
    conn.commit()
    print("  ✅ Created")


def verify_migration(conn: sqlite3.Connection) -> bool:
    """Verify that all expected structures are present."""
    print("\n── Verification ──")
    success = True

    # Check orders columns
    expected_order_cols = {
        "id", "conversation_id", "status", "created_at", "updated_at",
        "user_id", "course_id", "course_name", "amount", "currency",
        "internal_order_id", "razorpay_payment_link_id",
        "razorpay_payment_url", "razorpay_payment_id", "paid_at",
    }

    if table_exists(conn, "orders"):
        actual = get_existing_columns(conn, "orders")
        missing = expected_order_cols - actual
        if missing:
            print(f"  ⚠️  orders table missing columns: {missing}")
            success = False
        else:
            print("  ✅ orders table has all expected columns")

        # Verify existing data is preserved
        cursor = conn.execute("SELECT COUNT(*) FROM orders")
        count = cursor.fetchone()[0]
        print(f"  ℹ️  orders table has {count} existing rows")

    # Check closing_sessions
    if table_exists(conn, "closing_sessions"):
        print("  ✅ closing_sessions table exists")
    else:
        print("  ❌ closing_sessions table missing")
        success = False

    # Check webhook_events
    if table_exists(conn, "webhook_events"):
        print("  ✅ webhook_events table exists")
    else:
        print("  ❌ webhook_events table missing")
        success = False

    return success


def main():
    print("=" * 60)
    print("Bheem Closing-Agent Database Migration")
    print("=" * 60)

    if not DB_PATH.exists():
        print(f"\n⚠️  Database not found at {DB_PATH}")
        print("  The app will create it on first startup.")
        print("  Run the app first, then re-run this migration if needed.")
        sys.exit(0)

    # Step 1: Backup
    print(f"\nDatabase: {DB_PATH}")
    backup_path = backup_database(DB_PATH)

    # Step 2: Connect and migrate
    conn = sqlite3.connect(str(DB_PATH))
    try:
        migrate_orders_table(conn)
        create_closing_sessions_table(conn)
        create_webhook_events_table(conn)

        # Step 3: Verify
        success = verify_migration(conn)

        print("\n" + "=" * 60)
        if success:
            print("✅ Migration completed successfully!")
        else:
            print("⚠️  Migration completed with warnings — review above.")
        print(f"Backup: {backup_path}")
        print(f"Rollback: copy {backup_path} → {DB_PATH}")
        print("=" * 60)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
