"""
Servicio para guardar presupuestos de servicio con búsqueda/creación de cliente
y generación de notificación única por lote.
"""

from typing import Optional, Dict, List, Tuple
import base64
import hashlib
import hmac
import json
import os
import time
from services.supabase_client import supabase

DEFAULT_TIPO_VENTA_ID_SERVICIO = "8bd1ccec-bca7-46f9-bbcf-810cf8d1a929"
DEFAULT_ESTADO_NOTIFICACION_ID = "62369650-3a4f-4f99-9968-d4d27ae6de16"  # PENDIENTE
DEFAULT_TIPO_NOTIFICACION_SERVICIO_ID = "d6ca867a-28e2-4457-9981-889bbe1259d9"  # venta_servicio


def _build_jwt_temporal(cliente: Dict) -> str:
    """Genera un JWT temporal reutilizable por el panel de cliente."""
    secret = os.environ.get('JWT_SECRET', 'vidriobras-secret')
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": str(cliente['id_cliente']),
        "email": cliente.get('correo', ''),
        "name": cliente.get('nombre', ''),
        "exp": int(time.time()) + 7 * 24 * 3600,
        "aud": "cliente",
    }

    def b64url(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b'=').decode('utf-8')

    signing_input = f"{b64url(json.dumps(header).encode())}.{b64url(json.dumps(payload).encode())}"
    signature = hmac.new(secret.encode(), signing_input.encode(), hashlib.sha256).digest()
    return f"{signing_input}.{b64url(signature)}"


def buscar_cliente_por_documento(documento: str) -> Optional[Dict]:
    """
    Busca un cliente en la tabla 'cliente' por el campo 'documento'.
    Retorna el registro completo si lo encuentra, None si no.
    """
    try:
        result = supabase.table("cliente").select("*").eq("documento", documento).limit(1).execute()
        if result.data:
            return result.data[0]
        return None
    except Exception as e:
        print(f"Error buscando cliente por documento: {str(e)}")
        return None


def crear_cliente_temporal(documento: str, nombre_apis: str) -> Optional[Dict]:
    """
    Crea una cuenta temporal para un cliente no registrado.
    - correo     = nombre_sin_espacios_minusculas@vidriobras.com
    - contraseña = número de documento
    - cuenta_temporal = True
    """
    nombre_upper = (nombre_apis or documento).strip().upper()
    correo_base  = (nombre_apis or documento).strip().lower().replace(' ', '').replace('-', '')
    correo = f"{correo_base}@vidriobras.com"

    # Si ya existe ese correo, retornar el existente
    try:
        existente = supabase.table('cliente').select('*').eq('correo', correo).limit(1).execute()
        if existente.data:
            return existente.data[0]
    except Exception:
        pass

    cliente_data = {
        'nombre':             nombre_upper,
        'correo':             correo,
        'contraseña':         documento,
        'documento':          documento,
        'numero':             documento,
        'cuenta_temporal':    True,
        'registro_completo':  False,
    }
    try:
        result = supabase.table('cliente').insert(cliente_data).execute()
        if result.data:
            return result.data[0]
    except Exception as e:
        print(f"Error creando cliente temporal: {e}")
    return None


def guardar_multiples_presupuestos(
    presupuestos_list: List[Dict],
    documento: str,
    nombre_apis: str,
    fecha_remetro: Optional[str] = None,
    ubicacion: Optional[Dict] = None,
) -> Tuple[bool, str, List[str], Optional[Dict], bool, Optional[str]]:
    """
    Guarda múltiples presupuestos en la tabla 'presupuesto' y crea una sola
    notificación tipo 'servicio' que referencia los IDs generados.

    Flujo:
      1. Buscar cliente por documento en tabla cliente
      2. Si no existe → crear cuenta temporal
      3. Insertar cada presupuesto (servicio_id, descripcion, total, ancho, alto,
         fecha_remetro -- la fecha en la que se ira a tomar las medidas exactas)
      4. Si se envio ubicacion (direccion/referencia/lat/lng), guardar UNA fila
         en 'ubicacion' ligada al cliente y al primer presupuesto del lote
         (todo el lote comparte una sola visita de remetro)
      5. Crear UNA notificación con JSON: {presupuesto_ids, total_general, cantidad_servicios}

    Retorna:
    (success, message, presupuesto_ids, cliente_data, cliente_fue_creado, jwt_temporal)
    """
    try:
        # 1. Buscar cliente
        cliente      = buscar_cliente_por_documento(documento)
        cliente_creado = False

        # 2. Si no existe, crear cuenta temporal
        if not cliente:
            cliente = crear_cliente_temporal(documento, nombre_apis)
            if not cliente:
                return False, "No se pudo crear la cuenta temporal del cliente", [], None, False, None
            cliente_creado = True

        jwt_temporal = _build_jwt_temporal(cliente) if cliente_creado else None

        cliente_id     = cliente.get('id_cliente')
        nombre_cliente = cliente.get('nombre', nombre_apis.strip().upper())

        # 3. Insertar cada presupuesto en la tabla presupuesto (sin cliente_id)
        pres_ids       = []
        total_general  = 0.0
        ventas_creadas = []

        for pres in presupuestos_list:
            total = float(pres.get('total') or 0)
            ancho_val = pres.get('ancho')
            alto_val  = pres.get('alto')

            pres_insert: Dict = {
                'servicio_id': pres['servicio_id'],
                'descripcion': pres.get('descripcion') or pres.get('nombre_servicio') or '',
                'total':       round(total, 2),
            }
            if fecha_remetro:
                pres_insert['fecha_remetro'] = fecha_remetro
            if ancho_val:
                try:
                    pres_insert['ancho'] = float(ancho_val)
                except (ValueError, TypeError):
                    pass
            if alto_val:
                try:
                    pres_insert['alto'] = float(alto_val)
                except (ValueError, TypeError):
                    pass

            result = supabase.table('presupuesto').insert(pres_insert).execute()
            if result.data:
                pres_row = result.data[0]
                pres_id = pres_row.get('id_presupuesto')
                if pres_id:
                    pres_ids.append(pres_id)
                    total_general += total

                    # 3.1 Crear una venta ficticia de servicio asociada al cliente encontrado
                    # (sin carrito_id: es nullable y no hay carrito_compras real para un presupuesto)
                    venta_payload = {
                        'cliente_id': cliente_id,
                        'cantidad': 1,
                        'monto': round(total, 2),
                        'metodo': 'presupuesto',
                        'tipo_venta_id': DEFAULT_TIPO_VENTA_ID_SERVICIO,
                        'fecha_venta': time.strftime('%Y-%m-%d'),
                        'presupuesto_id': pres_id,
                    }
                    venta_res = supabase.table('venta').insert(venta_payload).execute()
                    if venta_res.data:
                        ventas_creadas.append(venta_res.data[0])

        if not pres_ids:
            return False, "No se pudieron guardar los presupuestos", [], cliente, cliente_creado, jwt_temporal

        # 4. Ubicacion para el remetro (una sola fila para todo el lote: es una
        # sola visita la que cubre todos los servicios presupuestados juntos).
        if ubicacion and ubicacion.get('latitud') is not None and ubicacion.get('longitud') is not None:
            try:
                supabase.table('ubicacion').insert({
                    'cliente_id':     cliente_id,
                    'presupuesto_id': pres_ids[0],
                    'direccion':      ubicacion.get('direccion'),
                    'referencia':     ubicacion.get('referencia'),
                    'latitud':        ubicacion.get('latitud'),
                    'longitud':       ubicacion.get('longitud'),
                }).execute()
            except Exception as exc_ubi:
                print(f"Error guardando ubicacion de remetro: {exc_ubi}")

        # 5. Crear una sola notificación por lote vinculada a la primera venta ficticia
        meta = {
            'presupuesto_ids':    pres_ids,
            'total_general':      round(total_general, 2),
            'cantidad_servicios': len(pres_ids),
        }
        notif_insert = {
            'nombre':      nombre_cliente,
            'descripcion': json.dumps(meta),
            'tipo':        'servicio',
            'tipo_notificacion_id': DEFAULT_TIPO_NOTIFICACION_SERVICIO_ID,
            'estado_notificacion_id': DEFAULT_ESTADO_NOTIFICACION_ID,
            'venta_id':    ventas_creadas[0].get('id_venta') if ventas_creadas else None,
        }
        supabase.table('notificacion').insert(notif_insert).execute()

        status_msg = "Cuenta temporal creada" if cliente_creado else "Cliente encontrado"
        msg = f"{len(pres_ids)} servicio(s) guardado(s) correctamente. {status_msg}."
        return True, msg, pres_ids, cliente, cliente_creado, jwt_temporal

    except Exception as e:
        print(f"Error en guardar_multiples_presupuestos: {str(e)}")
        import traceback
        traceback.print_exc()
        return False, f"Error del servidor: {str(e)}", [], None, False, None
