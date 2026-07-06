import sqlite3
print('start')
conn = sqlite3.connect(r'D:\A_zidonghuapingtai\auto_test_platform.db')
cur = conn.cursor()
tables = [t[0] for t in cur.execute('SELECT name FROM sqlite_master WHERE type=\"table\"').fetchall()]
print('TABLES:', tables)
conn.close()
