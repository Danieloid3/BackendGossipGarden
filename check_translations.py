import asyncio
from app.db.supabase import supabase

async def main():
    try:
        response = supabase.table("species_profile_translations").select("*").limit(1).execute()
        if response.data:
            print("Columns in species_profile_translations table:")
            for key, value in response.data[0].items():
                print(f"- {key}: {type(value).__name__}")
        else:
            print("No species_profile_translations found.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
