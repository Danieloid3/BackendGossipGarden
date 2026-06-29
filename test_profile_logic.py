import asyncio
import os
from app.db.supabase import supabase

async def main():
    try:
        plant_id = "e1db0480-8b23-4302-a752-405a45d311b5" # Plantita de la Suerte
        user_id = "f9c11ced-2085-4acf-996f-7c2320703132"
        
        # Test backend logic directly
        plant_res = supabase.table('plants').select('*, species(common_name, scientific_name)').eq('plant_id', plant_id).execute()
        print(f"Plant: {plant_res.data[0]['nickname']}")
        
        species_id = plant_res.data[0]['species_id']
        care_ranges_res = supabase.table('species_care_profiles').select('*').eq('species_id', species_id).execute()
        print(f"Care ranges exists: {bool(care_ranges_res.data)}")
        
        ai_res = supabase.table('species_ai_content').select('*').eq('species_id', species_id).limit(1).execute()
        print(f"AI content exists: {bool(ai_res.data)}")
        if ai_res.data:
            print(f"AI Tips: {ai_res.data[0].get('care_tips')}")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
