import asyncio
from app.db.supabase import supabase

async def main():
    try:
        response = supabase.table("plants").select("*").execute()
        for plant in response.data:
            print(f"--- Planta: {plant.get('nickname')} ---")
            print(f"plant_id: {plant['plant_id']}")
            print(f"species_id: {plant['species_id']}")
            print(f"photo_storage_path: {plant.get('photo_storage_path')}")
            print(f"health_status: {plant.get('health_status')}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
