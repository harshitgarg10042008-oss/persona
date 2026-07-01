import sqlite3
conn = sqlite3.connect('db.sqlite3')
tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
with open('tables.txt', 'w') as f:
    f.write('\n'.join(tables))
