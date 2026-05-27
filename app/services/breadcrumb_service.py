import requests
from flask import request

# Esta función se debe llamar en cada cambio de ruta en el frontend
# para actualizar el historial de breadcrumbs en el backend

def updateBreadcrumb(path, label) -> None:
    try:
        requests.post(
            f"{request.host_url.rstrip('/')}/api/breadcrumbs",
            json={"path": path, "label": label},
            timeout=2
        )
    except Exception:
        pass

# Ejemplo de uso:
# updateBreadcrumb('/dashboard', 'Dashboard')
# updateBreadcrumb('/clientes', 'Clientes')
