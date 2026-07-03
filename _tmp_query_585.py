import sqlite3, json

conn = sqlite3.connect("d:/A_zidonghuapingtai/auto_test_platform.db")
cur = conn.cursor()

# 查 id=585 的完整记录
cur.execute("SELECT * FROM test_record WHERE id=585")
row = cur.fetchone()
if row:
    col_names = [d[0] for d in cur.description]
    for k, v in zip(col_names, row):
        if v is not None:
            val = str(v)
            if len(val) > 300:
                val = val[:300] + "..."
            print(f"  {k}: {val}")
        else:
            print(f"  {k}: None")
else:
    print("No record for id=585")

# 读 log
cur.execute("SELECT log FROM test_record WHERE id=585")
row2 = cur.fetchone()
if row2 and row2[0]:
    log = json.loads(row2[0])
    print("\n=== steps ===")
    for step in log.get("steps", []):
        print(f"  {step['name']}: success={step.get('success')}, msg={step.get('msg', '')[:80]}")

conn.close()