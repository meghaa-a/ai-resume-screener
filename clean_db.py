import sqlite3

conn = sqlite3.connect("database.db")
c = conn.cursor()

c.execute("""
DELETE FROM jobs
WHERE id NOT IN (
    SELECT MIN(id)
    FROM jobs
    GROUP BY title
)
""")

conn.commit()
conn.close()

print("Duplicates removed successfully ✅")