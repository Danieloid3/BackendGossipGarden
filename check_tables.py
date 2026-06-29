import asyncio
import os
from supabase import create_client

async def main():
    try:
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_KEY")
        supabase = create_client(url, key)
        
        # We can't directly list tables with postgrest, but we can query information_schema or just fetch a known table and look for related ones
        response = supabase.table("species_care_profile_translations").select("*").limit(1).execute()
        print("Table species_care_profile_translations:")
        if response.data:
            for key, value in response.data[0].items():
                print(f"- {key}: {type(value).__name__}")
        else:
            print("Empty but exists")
    except Exception as e:
        print(f"Error checking species_care_profile_translations: {e}")
        
    try:
        response = supabase.table("species_profile_i18n").select("*").limit(1).execute()
        print("Table species_profile_i18n:")
        if response.data:
            for key, value in response.data[0].items():
                print(f"- {key}: {type(value).__name__}")
        else:
            print("Empty but exists")
    except Exception as e:
        print(f"Error checking species_profile_i18n: {e}")

if __name__ == "__main__":
    main()
