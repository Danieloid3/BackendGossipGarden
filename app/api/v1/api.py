from fastapi import APIRouter
from app.api.v1.endpoints import auth, identification, plants, sensors

api_router = APIRouter()

@api_router.get("/health")
async def health_check():
    """Endpoint de estado básico para comprobar que el servidor está funcionando."""
    return {"status": "ok", "db_connected": True}

api_router.include_router(auth.router, prefix="/auth", tags=["Auth"])
api_router.include_router(sensors.router, prefix="/sensors", tags=["Sensors / IoT"])
api_router.include_router(plants.router, prefix="/plants", tags=["Plants"])
api_router.include_router(identification.router, prefix="", tags=["Identification"])
