import psycopg2

host = "aws-0-us-east-1.pooler.supabase.com"
port = 6543
password = "EJPcTVZYW4qsWunQ"
dbname = "postgres"

db_url = f"postgresql://postgres:{password}@{host}:{port}/{dbname}?options=project%3Dtslrtebdziilekddalcr"

print(f"Connecting to {host} with project option...")
try:
    conn = psycopg2.connect(db_url, connect_timeout=10)
    print("SUCCESS!")
    
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS preferred_language VARCHAR(5) DEFAULT 'es';")
    print("Column added successfully.")
    cur.close()
    conn.close()
except Exception as e:
    print(f"Failed: {e}")
