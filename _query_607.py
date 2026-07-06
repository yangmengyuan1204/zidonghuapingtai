import sqlite3
conn = sqlite3.connect(r"D:\A_zidonghuapingtai\auto_test_platform.db")
cur = conn.cursor()
tables = [t[0] for t in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
print("TABLES:", tables)
for t in tables:
    try:
        rows = cur.execute(f"SELECT * FROM {t} WHERE id=607").fetchall()
        if rows:
            cols = [d[0] for d in cur.description]
            print(f"=== {t} id=607 ===")
            for row in rows:
                for c, v in zip(cols, row):
                    val = str(v)[:500] if v is not None else "None"
                    print(f"  {c}: {val}")
    except Exception as e:
        print(f"{t}: ERR {e}")
conn.close()
