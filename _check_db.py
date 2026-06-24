import sqlite3
conn = sqlite3.connect('auto_test_platform.db')
cursor = conn.cursor()
cursor.execute('PRAGMA table_info(functional_task)')
print('functional_task columns:')
for col in cursor.fetchall():
    print(col)
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
print('\nAll tables:')
for t in cursor.fetchall():
    print(t[0])
conn.close()
