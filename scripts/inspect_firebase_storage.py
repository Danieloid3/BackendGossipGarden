import os
import sys
from dotenv import load_dotenv
import firebase_admin
from firebase_admin import credentials, storage

# Load environment variables
script_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(script_dir)
env_path = os.path.join(parent_dir, '.env')

if os.path.exists(env_path):
    load_dotenv(dotenv_path=env_path)
else:
    load_dotenv()

cred_path = os.path.join(parent_dir, 'firebase_credentials.json')
bucket_name = os.environ.get("FIREBASE_STORAGE_BUCKET", "gossipgarden-e2879.firebasestorage.app")

if not os.path.exists(cred_path):
    print(f"Error: No se encontró {cred_path}")
    sys.exit(1)

print(f"Inicializando Firebase con credenciales de {cred_path}...")
print(f"Bucket de Storage a listar: {bucket_name}")

cred = credentials.Certificate(cred_path)
try:
    firebase_admin.initialize_app(cred, {
        'storageBucket': bucket_name
    })
    
    bucket = storage.bucket()
    print("Listando blobs en el bucket...")
    blobs = list(bucket.list_blobs())
    
    print(f"\n=== ARCHIVOS EN EL BUCKET ({len(blobs)}) ===")
    for b in blobs:
        print(f"- Path: {b.name} | Size: {b.size} bytes | ContentType: {b.content_type} | Updated: {b.updated}")
        
except Exception as e:
    print(f"Ocurrió un error: {e}")
