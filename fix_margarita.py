import asyncio
from app.db.supabase import supabase
from app.db.firebase import firebase_db

async def main():
    try:
        # Get Margarita plant
        response = supabase.table("plants").select("*").eq("nickname", "Margarita").execute()
        if not response.data:
            print("Margarita no encontrada.")
            return
        
        margarita = response.data[0]
        user_id = margarita["user_id"]
        plant_id = margarita["plant_id"]
        
        print(f"Margarita found! user_id: {user_id}, plant_id: {plant_id}")
        
        # Query firebase plant_identifications for this user_id
        docs = firebase_db.collection("plant_identifications").where("user_id", "==", user_id).stream()
        
        records = []
        for doc in docs:
            records.append(doc.to_dict())
            
        # Sort in python
        records.sort(key=lambda x: x.get("identified_at"), reverse=True)
        
        latest_path = None
        for record in records:
            if record.get("storage_path"):
                latest_path = record.get("storage_path")
                print(f"Found storage path in Firebase: {latest_path}")
                break
                
        if latest_path:
            # Update Margarita in Supabase
            update_response = supabase.table("plants").update({"photo_storage_path": latest_path}).eq("plant_id", plant_id).execute()
            print(f"Update response: {update_response.data}")
            print("Margarita updated successfully!")
        else:
            print("No storage path found in recent identifications.")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
