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
) -> Tuple[bool, str, List[str], Optional[Dict], bool, Optional[str]]:
    """
    Guarda múltiples presupuestos en la tabla 'presupuesto' y crea una sola
    notificación tipo 'servicio' que referencia los IDs generados.

    Flujo:
      1. Buscar cliente por documento en tabla cliente
      2. Si no existe → crear cuenta temporal
      3. Insertar cada presupuesto (cliente_id, servicio_id, descripcion, total, ancho, alto)
      4. Crear UNA notificación con JSON: {presupuesto_ids, total_general, cantidad_servicios}

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

        # 3. Insertar cada presupuesto con el schema real de la tabla
        pres_ids       = []
        total_general  = 0.0

        for pres in presupuestos_list:
            total = float(pres.get('total') or 0)
            ancho_val = pres.get('ancho')
            alto_val  = pres.get('alto')

            pres_insert: Dict = {
                'cliente_id':  cliente_id,
                'servicio_id': pres['servicio_id'],
                'descripcion': pres.get('descripcion') or pres.get('nombre_servicio') or '',
                'total':       round(total, 2),
            }
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
                pres_ids.append(result.data[0].get('id_presupuesto'))
                total_general += total

        if not pres_ids:
            return False, "No se pudieron guardar los presupuestos", [], cliente, cliente_creado, jwt_temporal

        # 4. Crear una sola notificación por lote
        meta = {
            'presupuesto_ids':    pres_ids,
            'total_general':      round(total_general, 2),
            'cantidad_servicios': len(pres_ids),
        }
        notif_insert = {
            'nombre':      nombre_cliente,
            'descripcion': json.dumps(meta),
            'tipo':        'servicio',
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
