from fastapi.testclient import TestClient
from app.main import app
from app.core.security import get_current_user

# Sobrescribir la dependencia para devolver un user_id de prueba
def override_get_current_user():
    return "test-user-id"

app.dependency_overrides[get_current_user] = override_get_current_user

client = TestClient(app)

with open("/home/lotus/Downloads/Tulipan_(Ama).jpeg", "rb") as f:
    files = {"image": ("Tulipan_(Ama).jpeg", f, "image/jpeg")}
    data = {
        "latitude": "6.2442",
        "longitude": "-75.5812",
        "output_language": "es"
    }
    print("Enviando petición a la API local (vía TestClient)...")
    resp = client.post("/api/v1/identify", data=data, files=files)
    
print("Status Code:", resp.status_code)
print("Response JSON:")
print(resp.json())
