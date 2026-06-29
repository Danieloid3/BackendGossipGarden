from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.schemas.auth import UserLogin, UserRegister, TokenResponse
from app.db.supabase import supabase
from supabase import create_client
from app.core.config import settings

router = APIRouter()

@router.post("/register")
async def register(user_in: UserRegister):
    try:
        # Cliente efímero para no mutar la sesión del singleton de Supabase
        local_supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
        response = local_supabase.auth.sign_up({
            "email": user_in.email,
            "password": user_in.password,
            "options": {
                "data": {
                    "username": user_in.username
                }
            }
        })
        return {
            "status": "success",
            "message": "Usuario registrado exitosamente. Revisa tu correo si tienes confirmación activada.",
            "user_id": response.user.id if response.user else None
        }
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Error al registrar usuario: {str(e)}"
        )

@router.post("/login", response_model=TokenResponse)
async def login(user_in: UserLogin):
    try:
        # Cliente efímero para no mutar la sesión del singleton de Supabase
        local_supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
        response = local_supabase.auth.sign_in_with_password({
            "email": user_in.email,
            "password": user_in.password
        })

        if not response.session:
            raise HTTPException(status_code=401, detail="Error en inicio de sesión, no se recibió sesión.")

        return TokenResponse(
            access_token=response.session.access_token,
            token_type="Bearer",
            refresh_token=response.session.refresh_token
        )
    except Exception as e:
        raise HTTPException(
            status_code=401,
            detail="Credenciales inválidas"
        )

@router.get("/google-url")
async def get_google_auth_url(redirect_to: str = "http://localhost:3000/auth/callback"):
    """
    Devuelve la URL a la que el frontend debe redirigir al usuario
    para iniciar el flujo de OAuth con Google.
    """
    try:
        local_supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
        response = local_supabase.auth.sign_in_with_oauth({
            "provider": "google",
            "options": {
                "redirect_to": redirect_to
            }
        })

        return {
            "status": "success",
            "url": response.url
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error obteniendo la URL de Google Auth: {str(e)}"
        )

class RefreshRequest(BaseModel):
    refresh_token: str

@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(req: RefreshRequest):
    try:
        local_supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
        response = local_supabase.auth.refresh_session(req.refresh_token)
        if not response.session:
            raise HTTPException(status_code=401, detail="No se pudo renovar la sesión")
            
        return TokenResponse(
            access_token=response.session.access_token,
            token_type="Bearer",
            refresh_token=response.session.refresh_token
        )
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Token expirado o inválido: {str(e)}")
