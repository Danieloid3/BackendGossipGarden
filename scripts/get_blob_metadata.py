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

print(f"=== METADATA PARA {blob_path} ===")
print(f"Content Type: {blob.content_type}")
print(f"Metadata: {blob.metadata}")
print(f"Custom Metadata: {blob.custom_time}")
print(f"Time Created: {blob.time_created}")
print(f"Cache Control: {blob.cache_control}")
print(f"Component Count: {blob.component_count}")
print(f"ETag: {blob.etag}")
print(f"Generation: {blob.generation}")
print(f"ID: {blob.id}")
print(f"MD5 Hash: {blob.md5_hash}")

# Generar un Signed URL para ver si funciona
try:
    from datetime import timedelta
    signed_url = blob.generate_signed_url(expiration=timedelta(hours=1))
    print(f"\nSigned URL (Válido por 1 hora):\n{signed_url}")
except Exception as e:
    print(f"No se pudo generar Signed URL: {e}")
