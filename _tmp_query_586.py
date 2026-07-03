import sqlite3, json

conn = sqlite3.connect("d:/A_zidonghuapingtai/auto_test_platform.db")
cur = conn.cursor()

# 查看 test_record 完整字段
cur.execute("PRAGMA table_info(test_record)")
cols = [r[1] for r in cur.fetchall()]
print("Cols:", cols)

# 查 id=586 完整记录
cur.execute("SELECT * FROM test_record WHERE id=586")
row = cur.fetchone()
for k, v in zip(cols, row):
    val = str(v) if v is not None else None
    if val and len(val) > 300:
        val = val[:300] + "..."
    print(f"  {k}: {val}")

# 查相关的 api_case
cur.execute("SELECT * FROM api_case WHERE id IN (SELECT case_id FROM test_record WHERE id=586)")
row2 = cur.fetchone()
if row2:
    print("\n--- api_case ---")
    cur.execute("PRAGMA table_info(api_case)")
    cols2 = [r[1] for r in cur.fetchall()]
    for k, v in zip(cols2, row2):
        val = str(v) if v is not None else None
        if val and len(val) > 300:
            val = val[:300] + "..."
        print(f"  {k}: {val}")

conn.close()