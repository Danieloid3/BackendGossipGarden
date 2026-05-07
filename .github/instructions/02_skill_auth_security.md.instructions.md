# SKILL: Autenticación JWT Asimétrica (Supabase)

## Objetivo
Crear el middleware/dependencia de seguridad en `app/core/security.py` para validar los tokens de acceso que envían los clientes móviles.

## Reglas de Implementación
1. **Librería principal:** Utiliza `PyJWT` (`pip install PyJWT`).
2. **Lectura de Llaves Públicas (JWKS):** 
   - El proyecto utiliza firmas ECC (P-256). NUNCA intentes validar usando un secreto de texto plano (HS256).
   - Instancia globalmente `PyJWKClient(settings.SUPABASE_JWKS_URL)`.
3. **Dependencia de FastAPI:**
   - Crea una función asíncrona `get_current_user(token: HTTPAuthorizationCredentials = Depends(HTTPBearer()))`.
   - Extrae el token, obtén la `signing_key` usando `jwk_client.get_signing_key_from_jwt(token)`.
   - Decodifica el token usando `jwt.decode(..., algorithms=["ES256"], audience="authenticated")`.
   - Captura `jwt.ExpiredSignatureError` y `jwt.InvalidTokenError`, lanzando `HTTPException(401)` con mensajes descriptivos.
   - Retorna el UUID del usuario extraído del campo `sub` del payload.