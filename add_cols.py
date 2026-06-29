import asyncio
from app.db.supabase import supabase

async def main():
    try:
        res = supabase.rpc('execute_sql', {'sql_string': 'ALTER TABLE species_ai_content ADD COLUMN IF NOT EXISTS personality_traits JSONB DEFAULT \'[]\'::jsonb; ALTER TABLE species_ai_content ADD COLUMN IF NOT EXISTS personality_description TEXT;'}).execute()
        print("Columns added using RPC!")
    except Exception as e:
        print("RPC failed, trying raw query...", e)
        # We can't do raw queries from client, but we can do it using postgres
        
if __name__ == '__main__':
    asyncio.run(main())
