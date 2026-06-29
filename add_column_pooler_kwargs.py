import psycopg2

host = "aws-0-us-east-1.pooler.supabase.com"
port = 6543
password = "EJPcTVZYW4qsWunQ"
dbname = "postgres"

users_to_try = [
    "postgres",
    "postgres.tslrtebdziilekddalcr",
    "tslrtebdziilekddalcr",
    "postgres@tslrtebdziilekddalcr"
]

for u in users_to_try:
    print(f"Trying user: {u}")
    try:
        conn = psycopg2.connect(
            host=host,
            port=port,
            user=u,
            password=password,
            dbname=dbname,
            connect_timeout=5
        )
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
