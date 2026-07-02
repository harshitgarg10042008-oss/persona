import sqlite3
import json

db_path = "c:/Users/vishe/OneDrive/Desktop/Samyak/persona/db.sqlite3"
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

cursor.execute("SELECT * FROM AnalysisAPI_assessmentsnapshot WHERE assessment_id = 31 LIMIT 2")
for s in cursor.fetchall():
    print(f"ID={s['id']} TYPE={s['analysis_type']} SCORE={s['score']}")
    print(s['analysis_data'])

conn.close()
