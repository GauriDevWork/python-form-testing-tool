# create_db.py
import sqlite3, os

# The database file will be created in your current directory
DB_PATH = os.path.join(os.getcwd(), "jobs.db")

# Define the SQL schema (tables)
DDL = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    url TEXT,
    timestamp TEXT,
    result TEXT,
    job_log TEXT,
    artifacts TEXT,
    report TEXT
);

CREATE TABLE IF NOT EXISTS schedules (
    id TEXT PRIMARY KEY,
    url TEXT,
    form_selector TEXT,
    mapping TEXT,
    cron_expr TEXT,
    created_at TEXT
);
"""

def main():
    print("Creating SQLite database at:", DB_PATH)
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.executescript(DDL)
    conn.commit()
    conn.close()
    print("✅ Database created successfully!")

if __name__ == "__main__":
    main()
