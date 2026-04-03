"""Check the processed_ids database."""
import sqlite3
import os

db_path = os.path.join(os.getcwd(), "processed_ids.db")
print(f"DB: {db_path}")
print(f"Exists: {os.path.exists(db_path)}")

if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    tables = c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    print(f"Tables: {tables}")
    for t in tables:
        tname = t[0]
        count = c.execute(f"SELECT COUNT(*) FROM [{tname}]").fetchone()[0]
        print(f"  {tname}: {count} rows")
        if count > 0 and count < 500:
            sample = c.execute(f"SELECT * FROM [{tname}] ORDER BY ROWID DESC LIMIT 5").fetchall()
            for s in sample:
                print(f"    {str(s)[:120]}")
    conn.close()
else:
    print("No database found - first crawl will create it")
