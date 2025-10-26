# app/db_utils.py
from datetime import datetime
import sqlite3, json, os
from typing import List, Optional, Dict

ROOT = os.getcwd()
DB_PATH = os.path.join(ROOT, "jobs.db")

def get_conn():
    """Get SQLite connection"""
    return sqlite3.connect(DB_PATH, timeout=30)

def save_job_record(record: Dict):
    """Save a completed test job to the DB"""
    if "timestamp" not in record:
        record["timestamp"] = datetime.datetime.utcnow().isoformat()
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT OR REPLACE INTO jobs (id,url,timestamp,result,job_log,artifacts,report) VALUES (?,?,?,?,?,?,?)",
        (
            record["job_id"],
            record["url"],
            record["timestamp"],
            record["result"],
            json.dumps(record.get("job_log", [])),
            json.dumps(record.get("artifacts", [])),
            record.get("report", ""),
        ),
    )
    conn.commit()
    conn.close()

def query_jobs(search: Optional[str] = None, limit: int = 50) -> List[Dict]:
    """Retrieve previous test runs"""
    conn = get_conn()
    cur = conn.cursor()
    if search:
        q = f"%{search}%"
        cur.execute(
            "SELECT id,url,timestamp,result,job_log,artifacts,report FROM jobs WHERE url LIKE ? OR result LIKE ? ORDER BY timestamp DESC LIMIT ?",
            (q, q, limit),
        )
    else:
        cur.execute(
            "SELECT id,url,timestamp,result,job_log,artifacts,report FROM jobs ORDER BY timestamp DESC LIMIT ?",
            (limit,),
        )
    rows = cur.fetchall()
    conn.close()

    out = []
    for r in rows:
        out.append(
            {
                "job_id": r[0],
                "url": r[1],
                "timestamp": r[2],
                "result": r[3],
                "job_log": json.loads(r[4]) if r[4] else [],
                "artifacts": json.loads(r[5]) if r[5] else [],
                "report": r[6],
            }
        )
    return out
