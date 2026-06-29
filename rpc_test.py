import os
from supabase import create_client
from dotenv import load_dotenv

load_dotenv(".env")
url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

supabase = create_client(url, key)
try:
    response = supabase.rpc('exec_sql', {'query': "ALTER TABLE users ADD COLUMN preferred_language VARCHAR(5) DEFAULT 'es';"}).execute()
    print("Success:", response)
except Exception as e:
    print("Error:", e)
