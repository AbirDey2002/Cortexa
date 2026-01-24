
import sys
import os
from sqlalchemy import create_engine, text

# Add backend directory to path to find config
# Add project root to path (Cortexa directory)
# Script is at backend/scripts/add_push_notification_col.py
# Root is ../../../
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from backend.core.config import DatabaseConfigs

def migrate():
    print(f"Connecting to database: {DatabaseConfigs.DATABASE_URL}")
    engine = create_engine(DatabaseConfigs.DATABASE_URL)
    
    with engine.connect() as conn:
        try:
            # Check if column exists
            result = conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='users' AND column_name='push_notification'"))
            if result.fetchone():
                print("Column 'push_notification' already exists. Skipping.")
                return

            print("Adding 'push_notification' column to 'users' table...")
            conn.execute(text("ALTER TABLE users ADD COLUMN push_notification BOOLEAN DEFAULT TRUE NOT NULL"))
            conn.commit()
            print("Migration successful!")
        except Exception as e:
            print(f"Error during migration: {e}")
            raise

if __name__ == "__main__":
    migrate()
