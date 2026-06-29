from typing import Optional
from pydantic import BaseModel, EmailStr, Field

class UserLogin(BaseModel):
    email: EmailStr = Field(..., description="Correo electrónico del usuario")
    password: str = Field(..., description="Contraseña del usuario")

class UserRegister(BaseModel):
    email: EmailStr = Field(..., description="Correo electrónico del usuario")
    password: str = Field(..., description="Contraseña del usuario (mínimo 6 caracteres)")
    username: str = Field(..., description="Nombre de usuario elegido")

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    refresh_token: Optional[str] = None
