import psycopg2

base_url = "aws-0-us-east-1.pooler.supabase.com:6543/postgres"
password = "EJPcTVZYW4qsWunQ"

users_to_try = [
    "postgres",
    "postgres.tslrtebdziilekddalcr",
    "tslrtebdziilekddalcr",
    "postgres@tslrtebdziilekddalcr"
]

for u in users_to_try:
    db_url = f"postgresql://{u}:{password}@{base_url}"
    print(f"Trying user: {u}")
    try:
        conn = psycopg2.connect(db_url, connect_timeout=5)
        print(f"SUCCESS with {u}")
        
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS preferred_language VARCHAR(5) DEFAULT 'es';")
        print("Column added successfully.")
        cur.close()
        conn.close()
        break
    except Exception as e:
        print(f"Failed: {e}")
