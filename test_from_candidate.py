import requests

data = {
    "candidate": {
        "scientific_name": "Anthemis cotula",
        "common_names": ["stinking chamomile"],
        "probability": 0.26,
        "gbif_id": 8035698,
        "inaturalist_id": 52841,
        "taxonomy": {}
    },
    "output_language": "es"
}

# we need an auth token or use TestClient
from fastapi.testclient import TestClient
from app.main import app
from app.core.security import get_current_user

def override_get_current_user():
    return "test-user-id"

app.dependency_overrides[get_current_user] = override_get_current_user

client = TestClient(app)
print("Testing /species/from-candidate...")
resp = client.post("/api/v1/species/from-candidate", json=data)

print(resp.status_code)
print(resp.text)
