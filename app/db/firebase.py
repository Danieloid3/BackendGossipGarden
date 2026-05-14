import firebase_admin
from firebase_admin import credentials, firestore
from app.core.config import settings
from google.cloud.firestore import Client
import json

if not firebase_admin._apps:
    if settings.FIREBASE_CREDENTIALS_JSON:
        cred_dict = json.loads(settings.FIREBASE_CREDENTIALS_JSON)
        cred = credentials.Certificate(cred_dict)
    else:
        cred = credentials.Certificate(settings.FIREBASE_CREDENTIALS_PATH)
    options = {"storageBucket": settings.FIREBASE_STORAGE_BUCKET} if settings.FIREBASE_STORAGE_BUCKET else {}
    firebase_admin.initialize_app(cred, options)

firebase_db: Client = firestore.client()
