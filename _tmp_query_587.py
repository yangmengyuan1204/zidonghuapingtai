import sqlite3, json

conn = sqlite3.connect("d:/A_zidonghuapingtai/auto_test_platform.db")
cur = conn.cursor()

cur.execute("PRAGMA table_info(test_record)")
cols = cur.fetchall()
print("Cols:", [c[1] for c in cols])

cur.execute("SELECT * FROM test_record WHERE id=587")
row = cur.fetchone()
col_names = [c[1] for c in cols]
for k, v in zip(col_names, row):
    if v is not None:
        val = str(v)
        if len(val) > 200:
            val = val[:200] + "..."
        print(f"  {k}: {val}")
    else:
        print(f"  {k}: None")

conn.close()