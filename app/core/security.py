import jwt
from jwt import PyJWKClient
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.core.config import settings

jwk_client = PyJWKClient(settings.SUPABASE_JWKS_URL)
security = HTTPBearer()

async def get_current_user(token: HTTPAuthorizationCredentials = Depends(security)) -> str:
    try:
        signing_key = jwk_client.get_signing_key_from_jwt(token.credentials)

        payload = jwt.decode(
            token.credentials,
            signing_key.key,
            algorithms=["ES256"],
            audience="authenticated"
        )

        user_uuid = payload.get("sub")
        if not user_uuid:
            raise HTTPException(status_code=401, detail="El token no contiene el UUID del usuario")

        return user_uuid

    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="El token ha expirado. Por favor, reauténticate.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token inválido.")
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Error validando el token: {str(e)}")
