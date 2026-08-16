# Configuración de Supabase para el backend Python (MVC)
# Este archivo inicializa la conexión y la instancia global de Supabase

import httpx
from supabase import create_client, Client
from supabase.lib.client_options import SyncClientOptions

# Configuración de Supabase
SUPABASE_URL = "https://zoafuvjfzawhvdrwnydo.supabase.co"
SUPABASE_SERVICE_ROLE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InpvYWZ1dmpmemF3aHZkcndueWRvIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc1NzQzNzkxMSwiZXhwIjoyMDczMDEzOTExfQ.HzjzDo1vLwDGJaMXGMH3TJIx80JALKF0S1LrPUk_kqg"

# En un entorno de producción, es mejor usar variables de entorno:
# url: str = os.environ.get("SUPABASE_URL")
# key: str = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

# Para desarrollo, usamos las claves directamente:
url: str = SUPABASE_URL
key: str = SUPABASE_SERVICE_ROLE_KEY

# Variable para verificar si la clave de servicio está disponible
IS_SERVICE = bool(key and key != "tu_service_role_key_aqui")

if not url or not key:
    raise ValueError("Las credenciales de Supabase no están configuradas.")

# postgrest-py abre su http_client interno con http2=True cuando no se le
# pasa uno propio. Con el proceso corriendo largo tiempo, esas conexiones
# HTTP/2 quedan pooled y el servidor (o un proxy intermedio) las cierra por
# inactividad; httpx no reintenta en una conexión nueva y explota con
# httpx.RemoteProtocolError: ConnectionTerminated en cualquier request que
# reuse esa conexión muerta. http2=False + retries evita quedar pegado en
# esa conexión zombie.
_http_client = httpx.Client(
    http2=False,
    transport=httpx.HTTPTransport(retries=2),
    timeout=httpx.Timeout(120),
)

supabase: Client = create_client(
    url, key, options=SyncClientOptions(httpx_client=_http_client)
)

# Note: For production do NOT commit service role keys. Set SUPABASE_SERVICE_ROLE_KEY in your environment.
__all__ = ['supabase']
