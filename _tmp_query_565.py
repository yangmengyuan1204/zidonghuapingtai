import sqlite3
c = sqlite3.connect('test_platform.db')
tables = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%record%'")]
print("tables:", tables)
for t in tables:
    cols = [r[1] for r in c.execute(f"PRAGMA table_info({t})")]
    print(f"\n[{t}] cols={cols}")
    try:
        row = c.execute(f"SELECT * FROM {t} WHERE id=565").fetchone()
        print("row:", row)
    except Exception as e:
        print("err:", e)
