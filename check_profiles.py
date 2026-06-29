import asyncio
from app.db.supabase import supabase

async def main():
    try:
        response = supabase.table("species_care_profiles").select("*").limit(1).execute()
        if response.data:
            print("Columns in species_care_profiles table:")
            for key, value in response.data[0].items():
                print(f"- {key}: {type(value).__name__}")
        else:
            print("No species_care_profiles found.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
