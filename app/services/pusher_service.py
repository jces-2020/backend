"""Servicio de notificaciones Pusher para Flutter y frontend."""
import os
from typing import Optional, Dict, Any
from datetime import datetime

# Intentar importar pusher; si no esta instalado funciona en modo degradado
try:
    import pusher as _pusher_lib
    _PUSHER_LIB_OK = True
except ImportError:
    _pusher_lib = None
    _PUSHER_LIB_OK = False

_pusher_client = None

CANAL_PRODUCTOS = 'productos-channel'
CANAL_NOTIFICACIONES = 'my-channel'
STOCK_BAJO_UMBRAL = 10


def obtener_diagnostico_pusher() -> Dict[str, Any]:
    """Devuelve estado de configuracion de Pusher para endpoints de debug."""
    app_id = os.environ.get('PUSHER_APP_ID', '').strip()
    key = os.environ.get('PUSHER_KEY', '').strip()
    secret = os.environ.get('PUSHER_SECRET', '').strip()
    cluster = os.environ.get('PUSHER_CLUSTER', '').strip()

    faltantes = []
    if not app_id:
        faltantes.append('PUSHER_APP_ID')
    if not key:
        faltantes.append('PUSHER_KEY')
    if not secret:
        faltantes.append('PUSHER_SECRET')
    if not cluster:
        faltantes.append('PUSHER_CLUSTER')

    return {
        'pusher_lib_instalada': _PUSHER_LIB_OK,
        'cliente_inicializado': _pusher_client is not None,
        'configurado': len(faltantes) == 0,
        'variables_faltantes': faltantes,
        'cluster': cluster or None,
        'key_masked': (key[:4] + '***' + key[-4:]) if len(key) >= 8 else ('***' if key else None),
    }


def _get_client():
    """Devuelve el cliente Pusher singleton, o None si no esta configurado."""
    global _pusher_client
    if _pusher_client is not None:
        return _pusher_client
    if not _PUSHER_LIB_OK:
        return None

    app_id = os.environ.get('PUSHER_APP_ID', '').strip()
    key    = os.environ.get('PUSHER_KEY', '7a1b11d5566b38ad05e6').strip()
    secret = os.environ.get('PUSHER_SECRET', '').strip()
    cluster = os.environ.get('PUSHER_CLUSTER', 'mt1').strip()

    if not app_id or not secret:
        print('[pusher_service] PUSHER_APP_ID / PUSHER_SECRET no configurados en .env')
        return None

    _pusher_client = _pusher_lib.Pusher(
        app_id=app_id,
        key=key,
        secret=secret,
        cluster=cluster,
        ssl=True,
    )
    return _pusher_client


def enviar_evento_pusher(
    data: Dict[str, Any],
    canal: str = CANAL_NOTIFICACIONES,
    evento: str = 'notificacion',
) -> bool:
    """Dispara un evento en un canal Pusher.

    Usado por notificacion_service y otros modulos del backend.
    Si Pusher no esta configurado, solo imprime en consola y retorna False.
    """
    try:
        client = _get_client()
        if client is None:
            print(f'[pusher_service] (sin cliente) evento omitido: {evento} -> {data}')
            return False
        client.trigger(canal, evento, data)
        print(f'[pusher_service] [OK] {canal}/{evento}')
        return True
    except Exception as e:
        print(f'[pusher_service] Error en evento {evento}: {e}')
        return False


def notificar_nuevo_producto(
    nombre: str,
    codigo: Optional[str] = None,
    producto_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Notifica la creacion de un nuevo producto en el canal de productos."""
    payload = {
        'tipo': 'producto_creado',
        'accion': 'CREADO',
        'mensaje': f'Nuevo producto agregado: {nombre}',
        'nombre': nombre,
        'codigo': codigo,
        'id': producto_id,
        'id_producto': producto_id,
        'timestamp': datetime.utcnow().isoformat(),
    }
    ok = enviar_evento_pusher(payload, canal=CANAL_PRODUCTOS, evento='producto_creado')
    return {'success': ok, 'message': 'Enviado' if ok else 'Sin conexion Pusher'}


def notificar_stock_actualizado(
    producto_id: str,
    nombre: str,
    cantidad_nueva: int,
    cantidad_anterior: Optional[int] = None,
    codigo: Optional[str] = None,
    imagen_url: Optional[str] = None,
) -> bool:
    """Notifica una reduccion de stock a Flutter.

    Dispara siempre el evento ``producto_actualizado`` (para recargar la lista)
    y adicionalmente ``stock_bajo`` si la cantidad nueva <= STOCK_BAJO_UMBRAL.
    """
    timestamp = datetime.utcnow().isoformat()
    cantidad_nueva = int(cantidad_nueva)
    print(
        f"[pusher_service] stock update producto_id={producto_id} nombre={nombre} "
        f"anterior={cantidad_anterior} nueva={cantidad_nueva}",
        flush=True,
    )

    # -- Evento general de stock actualizado ------------------------------
    enviar_evento_pusher(
        {
            'tipo': 'producto_actualizado',
            'accion': 'STOCK_ACTUALIZADO',
            'mensaje': f'Stock actualizado: {nombre} -> {cantidad_nueva} unidades',
            'nombre': nombre,
            'codigo': codigo,
            'id': producto_id,
            'id_producto': producto_id,
            'cantidad': cantidad_nueva,
            'cantidad_anterior': cantidad_anterior,
            'timestamp': timestamp,
        },
        canal=CANAL_PRODUCTOS,
        evento='producto_actualizado',
    )

    # -- Alerta de stock bajo ----------------------------------------------
    if cantidad_nueva <= STOCK_BAJO_UMBRAL:
        unidad = 'unidad' if cantidad_nueva == 1 else 'unidades'
        print(
            f"[pusher_service] stock bajo producto_id={producto_id} cantidad={cantidad_nueva}",
            flush=True,
        )
        enviar_evento_pusher(
            {
                'tipo': 'stock_bajo',
                'accion': 'STOCK_BAJO',
                'mensaje': f'[!] Stock bajo: {nombre} solo tiene {cantidad_nueva} {unidad}',
                'nombre': nombre,
                'codigo': codigo,
                'id': producto_id,
                'id_producto': producto_id,
                'cantidad': cantidad_nueva,
                'timestamp': timestamp,
            },
            canal=CANAL_PRODUCTOS,
            evento='stock_bajo',
        )
        
        enviar_notificacion_onesignal_stock_bajo(producto_id, nombre, cantidad_nueva, codigo, imagen_url)

    return True


def enviar_notificacion_onesignal_stock_bajo(
    producto_id: str,
    nombre: str,
    cantidad: int,
    codigo: Optional[str] = None,
    imagen_url: Optional[str] = None,
) -> bool:
    """Enviar push notifications a traves de OneSignal cuando stock <= 10."""
    try:
        from app.services.onesignal_service import (
            obtener_todos_player_ids_desde_bd,
            enviar_notificacion_stock_bajo
        )
        
        # Obtener todos los Player IDs registrados en OneSignal
        player_ids = obtener_todos_player_ids_desde_bd()
        
        if player_ids:
            resultado = enviar_notificacion_stock_bajo(
                player_ids,
                nombre,
                cantidad,
                codigo,
                imagen_url or ''
            )
            print(
                f"[pusher_service] onesignal enviadas={resultado.get('enviadas', 0)} "
                f"fallidas={resultado.get('fallidas', 0)}",
                flush=True,
            )
    
    except Exception as onesignal_err:
        print(f"[pusher_service] onesignal omitido: {onesignal_err}")
    
    return True
