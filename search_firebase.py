import asyncio
from app.db.firebase import firebase_db

async def main():
    try:
        # Query firebase plant_identifications for user
        # We need the one that corresponds to Manzanilla / Margarita
        docs = firebase_db.collection("plant_identifications").where("user_id", "==", "f9c11ced-2085-4acf-996f-7c2320703132").stream()
        
        records = []
        for doc in docs:
            records.append(doc.to_dict())
            
        records.sort(key=lambda x: x.get("identified_at"), reverse=True)
        
        print(f"Encontrados {len(records)} registros en Firebase.")
        
        for record in records:
            scientific = record.get("scientific_name", "")
            status = record.get("status", "")
            path = record.get("storage_path", "")
            date = record.get("identified_at")
            
            print(f"- Fecha: {date}")
            print(f"  Status: {status}")
            print(f"  Especie: {scientific}")
            print(f"  Path: {path}")
            print("---")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
