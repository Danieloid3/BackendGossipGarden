import asyncio
from app.db.supabase import supabase

async def main():
    try:
        response = supabase.table("species_ai_content").select("*").execute()
        for i, row in enumerate(response.data):
            print(f"Row {i}: species_id {row['species_id']}")
            print(f"  care_summary: {str(row.get('care_summary'))[:50]}")
            print(f"  care_tips: {str(row.get('care_tips'))[:50]}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
