import asyncio
from app.db.supabase import supabase

async def main():
    res = supabase.table('species_ai_content').select('species_id, ai_personality_prompt').execute()
    print(res.data)

if __name__ == '__main__':
    asyncio.run(main())
