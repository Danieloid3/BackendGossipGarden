import os
import sys
from dotenv import load_dotenv
from supabase import create_client

# Load environment variables from .env in parent directory
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

print(f"Conectando a Supabase en {url}...")
supabase = create_client(url, key)

try:
    # 1. Obtener información de la tabla de plantas
    response = supabase.table("plants").select("*").execute()
    plants = response.data
    
    print("\n=== PLANTAS EN LA BASE DE DATOS ===")
    print(f"Total plantas: {len(plants)}")
    for i, p in enumerate(plants, 1):
        print(f"\n{i}. Planta: {p.get('nickname')}")
        print(f"   ID: {p.get('plant_id')}")
        print(f"   Common Name: {p.get('common_name')}")
        print(f"   Scientific Name: {p.get('scientific_name')}")
        print(f"   Photo URL: {p.get('photo_url')}")
        print(f"   Photo Storage Path: {p.get('photo_storage_path')}")
        print(f"   User ID: {p.get('user_id')}")
        
    # 2. Obtener información de la tabla de usuarios para ver quiénes son
    try:
        user_response = supabase.table("users").select("*").execute()
        users = user_response.data
        print("\n=== USUARIOS EN LA BASE DE DATOS ===")
        print(f"Total usuarios: {len(users)}")
        for u in users:
            print(f"- UID: {u.get('uid')} | DisplayName: {u.get('displayName')} | Email: {u.get('email')}")
    except Exception as e:
        print(f"\nNo se pudo leer la tabla 'users': {e}")
        
except Exception as e:
    print(f"Ocurrió un error al consultar Supabase: {e}")
