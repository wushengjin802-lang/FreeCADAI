"""Check MySQL table structure for generation_tasks and api_keys."""
import pymysql

conn = pymysql.connect(
    host="119.29.16.170", port=3306,
    user="myroot", password="hsi!_eTX62028195",
    db="freecadai"
)
cur = conn.cursor()

print("=== generation_tasks columns ===")
cur.execute("SHOW COLUMNS FROM generation_tasks")
for row in cur.fetchall():
    print(f"  {str(row[0]):30} {str(row[1]):20} {str(row[2]):10} {str(row[4] or ''):10}")

print("\n=== api_keys columns ===")
cur.execute("SHOW COLUMNS FROM api_keys")
for row in cur.fetchall():
    print(f"  {str(row[0]):30} {str(row[1]):20} {str(row[2]):10} {str(row[4] or ''):10}")

print("\n=== Tasks by date ===")
cur.execute("SELECT COUNT(*), DATE(created_at) FROM generation_tasks GROUP BY DATE(created_at) ORDER BY 2 DESC LIMIT 10")
for row in cur.fetchall():
    print(f"  {row[0]} tasks on {row[1]}")

print("\n=== First task columns (sample) ===")
cur.execute("SELECT * FROM generation_tasks LIMIT 1")
col_names = [desc[0] for desc in cur.description]
print(f"  Columns: {col_names}")
row = cur.fetchone()
if row:
    for i, val in enumerate(row):
        print(f"  {col_names[i]:30} = {val}")

cur.close()
conn.close()
