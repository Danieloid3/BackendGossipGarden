from supabase import create_client, Client, ClientOptions
from app.core.config import settings
import httpx

# Prevenir 'RemoteProtocolError: Server disconnected' cerrando conexiones antes que el proxy de Supabase/Cloudflare
custom_httpx_client = httpx.Client(
    limits=httpx.Limits(keepalive_expiry=60.0),
    http2=False
)

supabase: Client = create_client(
    settings.SUPABASE_URL,
    settings.SUPABASE_SERVICE_ROLE_KEY,
    options=ClientOptions(httpx_client=custom_httpx_client)
)
