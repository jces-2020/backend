# -*- coding: utf-8 -*-
import requests
from typing import List, Dict
import os

ONESIGNAL_API_URL = 'https://onesignal.com/api/v1'


def enviar_notificacion_stock_bajo(
    player_ids: List[str],
    producto_nombre: str,
    cantidad_restante: int,
    codigo_producto: str,
    imagen_url: str = ''
) -> Dict[str, int]:
    """
    Envia notificacion push via OneSignal cuando stock <= 10

    Args:
        player_ids: Lista de OneSignal Player IDs
        producto_nombre: Nombre del producto
        cantidad_restante: Cantidad de stock restante
        codigo_producto: Codigo del producto

    Returns:
        Dict con {'enviadas': X, 'fallidas': Y}
    """
    try:
        app_id = os.getenv('ONESIGNAL_APP_ID', '')
        api_key = os.getenv('ONESIGNAL_API_KEY', '')

        if not player_ids:
            print('[onesignal_service] No hay Player IDs para notificar')
            return {'enviadas': 0, 'fallidas': 0}

        if not app_id or not api_key:
            print('[onesignal_service] ERROR: ONESIGNAL_APP_ID o ONESIGNAL_API_KEY no configurados')
            return {'enviadas': 0, 'fallidas': len(player_ids)}

        # Preparar payload de OneSignal
        headers = {
            'Authorization': f'Basic {api_key}',
            'Content-Type': 'application/json; charset=utf-8'
        }

        payload = {
            'app_id': app_id,
            'include_player_ids': player_ids,
            'headings': {
                'en': 'Low Stock - Place Your Order',
                'es': 'Stock Bajo - Realiza tu Pedido',
            },
            'contents': {
                'en': f'{producto_nombre} only has {cantidad_restante} units left. Place your order now.',
                'es': f'{producto_nombre} solo tiene {cantidad_restante} unidades restantes. Realiza tu pedido ahora.',
            },
            'data': {
                'producto': producto_nombre,
                'cantidad': str(cantidad_restante),
                'codigo': codigo_producto,
                'tipo': 'stock_bajo'
            }
        }

        # Adjuntar imagen si viene una URL valida para enriquecer la notificacion.
        if isinstance(imagen_url, str) and imagen_url.strip().lower().startswith(('http://', 'https://')):
            img = imagen_url.strip()
            payload['big_picture'] = img          # Android
            payload['chrome_web_image'] = img     # Web push
            payload['ios_attachments'] = {'img': img}  # iOS

        print(f'[onesignal_service] Enviando notificacion a {len(player_ids)} dispositivos')
        print(f'[onesignal_service] Producto: {producto_nombre}, Stock: {cantidad_restante}')

        response = requests.post(
            f'{ONESIGNAL_API_URL}/notifications',
            json=payload,
            headers=headers,
            timeout=10
        )

        if response.status_code == 200:
            result = response.json()
            print(f'[onesignal_service] Notificaciones enviadas exitosamente')
            print(f'[onesignal_service] Response: {result}')
            return {'enviadas': len(player_ids), 'fallidas': 0}
        else:
            print(f'[onesignal_service] Error en OneSignal API: {response.status_code}')
            print(f'[onesignal_service] Response: {response.text}')
            return {'enviadas': 0, 'fallidas': len(player_ids)}

    except Exception as e:
        print(f'[onesignal_service] Exception enviando notificaciones: {str(e)}')
        return {'enviadas': 0, 'fallidas': len(player_ids)}


def obtener_todos_player_ids_desde_bd() -> List[str]:
    """
    Obtiene todos los Player IDs registrados desde Supabase
    """
    try:
        from services.supabase_client import supabase
        
        response = supabase.table('uno_signal_tokens').select('player_id').execute()
        player_ids = [row['player_id'] for row in response.data]
        
        print(f'[onesignal_service] Obtenidos {len(player_ids)} Player IDs de BD')
        return player_ids
        
    except Exception as e:
        print(f'[onesignal_service] Error obteniendo Player IDs: {str(e)}')
        return []
