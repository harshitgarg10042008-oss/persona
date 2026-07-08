import sqlite3
from datetime import datetime

# Connect to the database
conn = sqlite3.connect('db.sqlite3')
cursor = conn.cursor()

# Query recent users
query = """
SELECT id, email, first_name, last_name, date_joined 
FROM UserAPI_customuser 
ORDER BY date_joined DESC 
LIMIT 5
"""

cursor.execute(query)
rows = cursor.fetchall()

print("Recent users (most recent first):")
print("=" * 80)
for row in rows:
    user_id, email, first_name, last_name, date_joined = row
    print(f"ID: {user_id}")
    print(f"Email: {email}")
    print(f"Name: {first_name} {last_name}")
    print(f"Joined: {date_joined}")
    print("-" * 40)

# Check for corresponding IndividualUser profiles
query_profiles = """
SELECT u.id, u.email, i.id as profile_id 
FROM UserAPI_customuser u 
LEFT JOIN UserAPI_individualuser i ON u.id = i.user_id 
ORDER BY u.date_joined DESC 
LIMIT 5
"""

cursor.execute(query_profiles)
profile_rows = cursor.fetchall()

print("\nUser profile creation check:")
print("=" * 80)
for row in profile_rows:
    user_id, email, profile_id = row
    status = "✓ Profile created" if profile_id else "✗ Profile missing"
    print(f"User ID {user_id} ({email}): {status}")

conn.close()
