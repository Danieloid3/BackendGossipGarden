import psycopg2
import os
from dotenv import load_dotenv

load_dotenv(".env")

# Direct connection URL constructed manually
db_url = "postgresql://postgres:EJPcTVZYW4qsWunQ@db.tslrtebdziilekddalcr.supabase.co:5432/postgres"

try:
    print(f"Connecting to {db_url}...")
    conn = psycopg2.connect(db_url)
    conn.autocommit = True
    cur = conn.cursor()
    
    cur.execute("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name='users' and column_name='preferred_language';
    """)
    if not cur.fetchone():
        print("Adding preferred_language column to users table...")
        cur.execute("ALTER TABLE users ADD COLUMN preferred_language VARCHAR(5) DEFAULT 'es';")
        print("Column added successfully.")
    else:
        print("Column preferred_language already exists.")
        
    cur.close()
    conn.close()
except Exception as e:
    print(f"Error: {e}")
