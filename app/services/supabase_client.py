# Configuración de Supabase para el backend Python (MVC)
# Este archivo inicializa la conexión y la instancia global de Supabase

from supabase import create_client, Client

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

supabase: Client = create_client(url, key)

# Note: For production do NOT commit service role keys. Set SUPABASE_SERVICE_ROLE_KEY in your environment.
__all__ = ['supabase']
