import os
import sys
from dotenv import load_dotenv
import firebase_admin
from firebase_admin import credentials, storage

script_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(script_dir)
env_path = os.path.join(parent_dir, '.env')

if os.path.exists(env_path):
    load_dotenv(dotenv_path=env_path)
else:
    load_dotenv()

cred_path = os.path.join(parent_dir, 'firebase_credentials.json')
bucket_name = os.environ.get("FIREBASE_STORAGE_BUCKET", "gossipgarden-e2879.firebasestorage.app")

cred = credentials.Certificate(cred_path)
firebase_admin.initialize_app(cred, {
    'storageBucket': bucket_name
})

bucket = storage.bucket()
blob_path = "plant_identifications/f9c11ced-2085-4acf-996f-7c2320703132/20260515T030211_Dracaena_trifasciata_eb71c4a8.jpeg"
blob = bucket.get_blob(blob_path)

if blob is None:
    print(f"Error: Blob {blob_path} no encontrado.")
    sys.exit(1)

print(f"Haciendo público el blob {blob_path}...")
try:
    blob.make_public()
    print("¡Éxito! El blob ahora es público.")
    print(f"URL pública: {blob.public_url}")
except Exception as e:
    print(f"Error al hacer público el blob: {e}")
