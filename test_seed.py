import os
import sqlite3
from pathlib import Path

# Ensure DB is deleted
db_path = Path("data/phantomeye.db")
if db_path.exists():
    db_path.unlink()

# Import and print config
import backend.config
print("CONFIG USERNAME:", backend.config.RTSP_USERNAME)

# Init DB and Seed
from backend.database.schema import init_db
from backend.database.seed_data import seed_database
init_db()
seed_database()

# Query DB
conn = sqlite3.connect(str(db_path))
c = conn.cursor()
c.execute("SELECT stream_url FROM cameras WHERE camera_id='CAM-001'")
res = c.fetchone()
print("DB URL:", res[0] if res else "None")
