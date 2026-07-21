"""One-time migration: add lead_profile column to the users table.

Run this script once if you have an existing bheem.db that was created
before the Lead Intelligence Agent feature was added.

Usage:
    python scripts/migrate_add_lead_profile.py
"""

import sqlite3
import sys
from pathlib import Path


def migrate():
    db_path = Path("data/bheem.db")
    if not db_path.exists():
        print(f"Database not found at {db_path}. Nothing to migrate.")
        print("The column will be created automatically when the app starts.")
        sys.exit(0)

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    # Check if column already exists
    cursor.execute("PRAGMA table_info(users)")
    columns = [row[1] for row in cursor.fetchall()]

    if "lead_profile" in columns:
        print("Column 'lead_profile' already exists. No migration needed.")
        conn.close()
        sys.exit(0)

    cursor.execute("ALTER TABLE users ADD COLUMN lead_profile TEXT")
    conn.commit()
    conn.close()
    print("Migration complete: added 'lead_profile' column to users table.")


if __name__ == "__main__":
    migrate()
