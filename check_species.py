import asyncio
from app.db.supabase import supabase

async def main():
    try:
        response = supabase.table("species").select("*").limit(1).execute()
        if response.data:
            print("Columns in species table:")
            for key, value in response.data[0].items():
                print(f"- {key}: {type(value).__name__}")
        else:
            print("No species found.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
