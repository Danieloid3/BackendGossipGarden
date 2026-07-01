import os
import sys
from dotenv import load_dotenv
from supabase import create_client

# Load environment variables
script_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(script_dir)
env_path = os.path.join(parent_dir, '.env')

if os.path.exists(env_path):
    load_dotenv(dotenv_path=env_path)
else:
    load_dotenv()

url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

if not url or not key:
    print("Error: SUPABASE_URL o SUPABASE_SERVICE_ROLE_KEY no encontrados en las variables de entorno.")
    sys.exit(1)

supabase = create_client(url, key)

plant_id = "e1db0480-8b23-4302-a752-405a45d311b5"
photo_path = "plant_identifications/f9c11ced-2085-4acf-996f-7c2320703132/20260515T030211_Dracaena_trifasciata_eb71c4a8.jpeg"

print(f"Asociando la imagen '{photo_path}' a la planta '{plant_id}' en Supabase...")

try:
    response = supabase.table("plants").update({
        "photo_storage_path": photo_path
    }).eq("plant_id", plant_id).execute()
    
    if len(response.data) > 0:
        print("¡Éxito! Planta actualizada correctamente:")
        p = response.data[0]
        print(f"Nickname: {p.get('nickname')} | photo_storage_path: {p.get('photo_storage_path')}")
    else:
        print(f"No se encontró la planta con ID {plant_id} para actualizar.")
        
except Exception as e:
    print(f"Error al actualizar la base de datos: {e}")
