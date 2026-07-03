import sqlite3

conn = sqlite3.connect("d:/A_zidonghuapingtai/auto_test_platform.db")
cur = conn.cursor()

# 查所有表
cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in cur.fetchall()]
print("Tables:", tables)

# 查用户表
for t in tables:
    if "user" in t.lower() or "account" in t.lower() or "auth" in t.lower():
        print(f"\n--- {t} ---")
        cur.execute(f"PRAGMA table_info({t})")
        cols = [r[1] for r in cur.fetchall()]
        print("Cols:", cols)
        cur.execute(f"SELECT * FROM {t} LIMIT 3")
        for row in cur.fetchall():
            for k, v in zip(cols, row):
                if k == "password":
                    print(f"  {k}: {str(v)[:30]}...")
                else:
                    print(f"  {k}: {v}")
            print("---")

conn.close()