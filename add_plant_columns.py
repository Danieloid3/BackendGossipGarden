import psycopg2

host = "aws-0-us-east-1.pooler.supabase.com"
port = 6543
password = "EJPcTVZYW4qsWunQ"
dbname = "postgres"

db_url = f"postgresql://postgres.tslrtebdziilekddalcr:{password}@{host}:{port}/{dbname}"

print(f"Connecting to {host} with project option...")
try:
    conn = psycopg2.connect(db_url, connect_timeout=10)
    print("SUCCESS!")
    
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("ALTER TABLE plants ADD COLUMN IF NOT EXISTS mac_address VARCHAR(20);")
    cur.execute("ALTER TABLE plants ADD COLUMN IF NOT EXISTS last_watered TIMESTAMP WITH TIME ZONE;")
    print("Columns added successfully.")
    cur.close()
    conn.close()
except Exception as e:
    print(f"Failed: {e}")
