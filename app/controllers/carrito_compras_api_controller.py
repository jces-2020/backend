from flask import Blueprint, request, jsonify
from app.services.supabase_client import supabase
import uuid
import os, json, base64, hmac, hashlib, time

carrito_compras_api = Blueprint('carrito_compras_api', __name__)

def _b64url_decode(data: str) -> bytes:
    rem = len(data) % 4
    if rem:
        data += '=' * (4 - rem)
    return base64.urlsafe_b64decode(data)

def verify_jwt(token: str):
    try:
        parts = token.split('.')
        if len(parts) != 3:
            return None
        header = json.loads(_b64url_decode(parts[0]).decode('utf-8'))
        payload = json.loads(_b64url_decode(parts[1]).decode('utf-8'))
        signature = parts[2]
        if header.get('alg') != 'HS256':
            return None
        secret = os.environ.get('JWT_SECRET', 'vidriobras-secret')
        signing_input = parts[0] + '.' + parts[1]
        expected = hmac.new(secret.encode('utf-8'), signing_input.encode('utf-8'), hashlib.sha256).digest()
        expected_b64 = base64.urlsafe_b64encode(expected).rstrip(b'=').decode('utf-8')
        if not hmac.compare_digest(signature, expected_b64):
            return None
        if payload.get('exp') and int(payload['exp']) < int(time.time()):
            return None
        return payload
    except Exception:
        return None

def _require_personal(request, allowed_areas=None):
    """Valida Authorization Bearer de personal y opcionalmente su Ã¡rea.
    Devuelve (ok: bool, payload_or_response) donde payload_or_response es el payload o una respuesta Flask."""
    auth = request.headers.get('Authorization', '')
    if not auth.startswith('Bearer '):
        return False, (jsonify({'success': False, 'message': 'No autorizado'}), 401)
    token = auth.split(' ', 1)[1]
    payload = verify_jwt(token)
    if not payload or payload.get('aud') != 'personal':
        return False, (jsonify({'success': False, 'message': 'Token invÃ¡lido'}), 401)
    if allowed_areas:
        area = (payload.get('area') or '').upper()
        # normalizar acentos bÃ¡sicos
        area = area.replace('Ã','A').replace('Ã‰','E').replace('Ã','I').replace('Ã“','O').replace('Ãš','U')
        allowed_norm = [a.upper().replace('Ã','A').replace('Ã‰','E').replace('Ã','I').replace('Ã“','O').replace('Ãš','U') for a in allowed_areas]
        if area not in allowed_norm:
            return False, (jsonify({'success': False, 'message': 'Ãrea no autorizada'}), 403)
    return True, payload

@carrito_compras_api.route('/api/carrito_compras', methods=['POST'])
def crear_o_obtener_carrito():
    """
    Endpoint que ya NO se debe usar para crear carritos.
    Los carritos se crean automÃ¡ticamente despuÃ©s del pago.
    Este endpoint devuelve un error deprecado.
    """
    return jsonify({
        'success': False,
        'message': 'Los carritos se crean automÃ¡ticamente despuÃ©s del pago. No uses este endpoint.'
    }), 410  # 410 Gone

@carrito_compras_api.route('/api/carrito_compras/<cliente_id>', methods=['GET'])
def obtener_carrito(cliente_id):
    try:
        result = supabase.table('carrito_compras').select('*').eq('cliente_id', cliente_id).execute()
        data = result.data or []
        pedidos = []
        for row in data:
            pedidos.append({
                'id': row.get('id_carrito'),
                'estado': row.get('estado') or 'Proceso'
            })
        return jsonify({'success': True, 'data': pedidos}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@carrito_compras_api.route('/api/carrito_compras/attach', methods=['POST', 'PATCH'])
def asociar_carrito_a_cliente():
    """
    DEPRECADO: Este endpoint NO DEBE USARSE.
    La asociaciÃ³n del cliente_id a carrito_compras SOLO debe hacerse mediante el webhook de Mercado Pago.
    carrito_compras es SOLO para pedidos ya pagados (barra de progreso).
    """
    return jsonify({
        'success': False, 
        'message': 'Este endpoint estÃ¡ deprecado. La asociaciÃ³n cliente-carrito se hace automÃ¡ticamente en el webhook de pago.'
    }), 410  # 410 Gone

@carrito_compras_api.route('/api/carrito_compras/verificar_pendiente', methods=['POST'])
def verificar_pedido_pendiente():
    """
    ELIMINADO: Ya no hay validaciÃ³n de 'pendiente'.
    Los productos se guardan SOLO despuÃ©s del pago.
    """
    return jsonify({
        'success': True,
        'tiene_pendiente': False,
        'message': 'ValidaciÃ³n eliminada - productos se guardan solo despuÃ©s del pago'
    }), 200


@carrito_compras_api.route('/api/carrito_compras/checkout', methods=['POST', 'PATCH'])
def confirmar_pedido():
    """Marca un carrito como 'pendiente' (o actualiza su estado) y asegura la asociaciÃ³n al cliente.
    body: { carrito_id, cliente_id, estado? }
    """
    data = request.get_json(silent=True) or {}
    carrito_id = data.get('carrito_id')
    cliente_id = data.get('cliente_id')
    estado = data.get('estado') or 'Proceso'
    if not carrito_id or not cliente_id:
        return jsonify({'success': False, 'message': 'carrito_id y cliente_id son requeridos'}), 400
    try:
        # ValidaciÃ³n por token: debe existir y coincidir con cliente_id
        auth = request.headers.get('Authorization', '')
        if not auth.startswith('Bearer '):
            return jsonify({'success': False, 'message': 'No autorizado'}), 401
        token = auth.split(' ', 1)[1]
        payload = verify_jwt(token)
        if not payload or str(payload.get('sub')) != str(cliente_id):
            return jsonify({'success': False, 'message': 'Token invÃ¡lido'}), 401

        # Asegurar asociaciÃ³n y estado (guardamos solo texto 'estado')
        upd_fields = {'cliente_id': cliente_id, 'estado': estado}

        try:
            upd = supabase.table('carrito_compras').update(upd_fields).eq('id_carrito', carrito_id).execute()
        except Exception:
            return jsonify({'success': False, 'message': 'No se pudo confirmar el pedido.'}), 400

        # Crear una notificaciÃ³n de trabajo con el nombre del cliente y cantidad total de productos
        try:
            # Datos del cliente
            cli_info = supabase.table('cliente').select('nombre').eq('id_cliente', cliente_id).limit(1).execute()
            nombre_cli = None
            if cli_info and getattr(cli_info, 'data', None):
                nombre_cli = cli_info.data[0].get('nombre')
            # Cantidad total de productos (suma de cantidades en el carrito)
            items = supabase.table('venta').select('cantidad').eq('carrito_id', carrito_id).execute()
            # NotificaciÃ³n de trabajo se crearÃ¡ solo cuando el pago estÃ© aprobado (webhook Mercado Pago)
            pass
        except Exception:
            pass

        return jsonify({'success': True, 'data': upd.data}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

## Endpoint de barra de progreso de pedidos eliminado temporalmente

@carrito_compras_api.route('/api/admin/pedidos/<cliente_id>', methods=['GET'])
def admin_listar_pedidos(cliente_id):
    """Lista pedidos de un cliente. Requiere JWT de personal (Ã¡rea ALMACEN o ADMINISTRACION)."""
    try:
        ok, resp = _require_personal(request, allowed_areas=['ALMACEN', 'ADMINISTRACION'])
        if not ok:
            return resp
        res = supabase.table('carrito_compras').select('*').eq('cliente_id', cliente_id).execute()
        carritos = res.data or []
        pedidos = []
        for c in carritos:
            estado_desc = c.get('estado')
            pedidos.append({
                'id': c.get('id_carrito'),
                'estado': estado_desc or 'Proceso',
                'created_at': c.get('created_at') or c.get('fecha')
            })
        pedidos.sort(key=lambda x: x.get('created_at') or '', reverse=True)
        return jsonify({'success': True, 'pedidos': pedidos}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@carrito_compras_api.route('/api/pedidos/<carrito_id>/estado', methods=['PATCH'])
def actualizar_estado_pedido(carrito_id):
    """Actualiza el estado de un pedido (carrito). body: { estado: 'Proceso'|'Pagado'|'Listo' }.
    PreferirÃ¡ guardar estado_id si existe la tabla estado.
    """
    data = request.get_json(silent=True) or {}
    estado_req = (data.get('estado') or '').strip()
    if not estado_req:
        return jsonify({'success': False, 'message': 'estado es requerido'}), 400
    try:
        # Solo personal autorizado puede cambiar el estado
        ok, resp = _require_personal(request, allowed_areas=['ALMACEN', 'ADMINISTRACION', 'OBRAS', 'TRABAJO'])
        if not ok:
            return resp
        # Validar que el carrito exista
        car = supabase.table('carrito_compras').select('id_carrito').eq('id_carrito', carrito_id).limit(1).execute()
        if not car.data:
            return jsonify({'success': False, 'message': 'Pedido no encontrado'}), 404
        upd_fields = {'estado': estado_req}
        upd = supabase.table('carrito_compras').update(upd_fields).eq('id_carrito', carrito_id).execute()

        # Intentar marcar la notificaciÃ³n asociada como atendida cuando el pedido queda Pagado/Listo
        try:
            estado_final = estado_req.strip().lower()
            if estado_final in ('listo', 'pagado'):
                # Resolver id de estado_notificacion 'Atendida' si existe
                atendida_id = None
                try:
                    estn = supabase.table('estado_notificacion').select('id_estado, descripcion').execute()
                    for row in getattr(estn, 'data', []) or []:
                        desc = (row.get('descripcion') or '').strip().lower()
                        if desc in ('atendida', 'cerrada', 'completada'):
                            atendida_id = row.get('id_estado')
                            break
                except Exception:
                    atendida_id = None
                # Buscar notificaciÃ³n vinculada a este carrito_id (descripcion guarda JSON con carrito_id)
                try:
                    nres = supabase.table('notificacion').select('id_notificacion, descripcion').execute()
                except Exception:
                    nres = None
                if nres and getattr(nres, 'data', None):
                    import json as _json
                    for n in nres.data:
                        try:
                            meta = _json.loads(n.get('descripcion') or '{}')
                            if isinstance(meta, dict) and str(meta.get('carrito_id')) == str(carrito_id):
                                if atendida_id is not None:
                                    try:
                                        supabase.table('notificacion').update({'estado_notificacion_id': atendida_id}).eq('id_notificacion', n.get('id_notificacion')).execute()
                                    except Exception:
                                        pass
                                # Si no hay tabla de estados, no hacemos nada (evitamos tocar esquema)
                                break
                        except Exception:
                            continue
            # Si se marca Pagado, completar el flujo: borrar items, carrito y notificaciones para liberar al cliente
            if estado_final == 'pagado':
                deleted_items = 0
                deleted_notifs = 0
                try:
                    # contar items
                    it = supabase.table('venta').select('producto_id').eq('carrito_id', carrito_id).execute()
                    deleted_items = len(getattr(it, 'data', []) or [])
                except Exception:
                    deleted_items = 0
                try:
                    # Las líneas de venta se conservan como historial; no se borran.
                    pass
                except Exception:
                    pass
                # borrar notificaciones asociadas
                try:
                    nres2 = supabase.table('notificacion').select('id_notificacion, descripcion').execute()
                    import json as _json
                    for n in getattr(nres2, 'data', []) or []:
                        try:
                            meta = _json.loads(n.get('descripcion') or '{}')
                            if isinstance(meta, dict) and str(meta.get('carrito_id')) == str(carrito_id):
                                supabase.table('notificacion').delete().eq('id_notificacion', n.get('id_notificacion')).execute()
                                deleted_notifs += 1
                        except Exception:
                            continue
                    # Fallback: si las notificaciones antiguas no tienen JSON, intentar por coincidencia de texto
                    try:
                        like_res = supabase.table('notificacion').select('id_notificacion').like('descripcion', f"%{carrito_id}%").execute()
                        for n in getattr(like_res, 'data', []) or []:
                            try:
                                supabase.table('notificacion').delete().eq('id_notificacion', n.get('id_notificacion')).execute()
                                deleted_notifs += 1
                            except Exception:
                                pass
                    except Exception:
                        pass
                except Exception:
                    pass
                # por Ãºltimo borrar el carrito
                try:
                    supabase.table('carrito_compras').delete().eq('id_carrito', carrito_id).execute()
                except Exception:
                    pass
                return jsonify({'success': True, 'data': upd.data, 'deleted': True, 'deleted_items': deleted_items, 'deleted_notifs': deleted_notifs}), 200
        except Exception:
            # No bloquear respuesta por errores en notificaciÃ³n
            pass

        return jsonify({'success': True, 'data': upd.data}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ========= NUEVO: Pedidos por cliente (para frontend cliente) =========
from app.controllers.clientes_controller import verify_jwt


@carrito_compras_api.route('/api/pedidos/<cliente_id>', methods=['GET'])
def listar_pedidos_cliente(cliente_id):
    """Lista pedidos de un cliente autenticado (usado por el frontend de cliente).
    Requiere JWT del cliente en Authorization: Bearer <token>.
    """
    try:
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return jsonify({'success': False, 'message': 'Token faltante'}), 401
        token = auth_header.split(' ', 1)[1]
        payload = verify_jwt(token)
        if not payload:
            return jsonify({'success': False, 'message': 'Token invÃ¡lido'}), 401
        if str(payload.get('sub')) != str(cliente_id):
            return jsonify({'success': False, 'message': 'No autorizado'}), 403

        res = supabase.table('carrito_compras').select('*').eq('cliente_id', cliente_id).execute()
        carritos = res.data or []
        pedidos = []
        for c in carritos:
            pedidos.append({
                'id': c.get('id_carrito'),
                'estado': c.get('estado') or 'Proceso',
                'created_at': c.get('created_at') or c.get('fecha')
            })
        pedidos.sort(key=lambda x: x.get('created_at') or '', reverse=True)
        return jsonify({'success': True, 'pedidos': pedidos}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@carrito_compras_api.route('/api/clientes/pedidos/<carrito_id>/auto_delete_entregado', methods=['DELETE'])
def auto_delete_pedido_entregado_cliente(carrito_id):
    """Elimina un pedido entregado/listo del cliente autenticado para evitar acumulación en el panel."""
    try:
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return jsonify({'success': False, 'message': 'Token faltante'}), 401

        token = auth_header.split(' ', 1)[1]
        payload = verify_jwt(token)
        if not payload:
            return jsonify({'success': False, 'message': 'Token inválido'}), 401

        # Buscar carrito
        cres = supabase.table('carrito_compras').select('id_carrito, estado').eq('id_carrito', carrito_id).limit(1).execute()
        if not getattr(cres, 'data', None):
            return jsonify({'success': True, 'deleted': False, 'message': 'Pedido ya no existe'}), 200

        carrito = cres.data[0]
        estado = str(carrito.get('estado') or '').strip().lower()
        if estado not in ('entregado', 'listo'):
            return jsonify({'success': False, 'message': 'Solo se puede eliminar pedidos entregados/listos'}), 400

        # El detalle ya se conserva en venta; no se borra historial.

        # Limpiar notificaciones asociadas por carrito_id en descripcion JSON o texto
        deleted_notifs = 0
        try:
            nres = supabase.table('notificacion').select('id_notificacion, descripcion').execute()
            for n in getattr(nres, 'data', []) or []:
                desc = n.get('descripcion') or ''
                should_delete = False
                try:
                    meta = json.loads(desc)
                    if isinstance(meta, dict) and str(meta.get('carrito_id')) == str(carrito_id):
                        should_delete = True
                except Exception:
                    if str(carrito_id) in str(desc):
                        should_delete = True

                if should_delete:
                    try:
                        supabase.table('notificacion').delete().eq('id_notificacion', n.get('id_notificacion')).execute()
                        deleted_notifs += 1
                    except Exception:
                        pass
        except Exception:
            pass

        # Eliminar carrito
        supabase.table('carrito_compras').delete().eq('id_carrito', carrito_id).execute()

        return jsonify({
            'success': True,
            'deleted': True,
            'carrito_id': carrito_id,
            'deleted_notifs': deleted_notifs
        }), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@carrito_compras_api.route('/api/carrito_compras/limpiar_carritos_vacios', methods=['POST'])
def limpiar_carritos_vacios():
    """
    Elimina todos los carritos del cliente que estÃ¡n vacÃ­os (sin productos)
    o que tienen estado Pendiente con cliente_id
    """
    try:
        data = request.get_json(silent=True) or {}
        cliente_id = data.get('cliente_id')
        
        if not cliente_id:
            return jsonify({'success': False, 'message': 'cliente_id requerido'}), 400
        
        # Validar token
        auth = request.headers.get('Authorization', '')
        if not auth.startswith('Bearer '):
            return jsonify({'success': False, 'message': 'No autorizado'}), 401
        token = auth.split(' ', 1)[1]
        payload = verify_jwt(token)
        if not payload or str(payload.get('sub')) != str(cliente_id):
            return jsonify({'success': False, 'message': 'Token invÃ¡lido'}), 401
        
        print(f"\n[LIMPIAR_CARRITOS] Cliente: {cliente_id}")
        
        # Obtener TODOS los carritos del cliente
        carritos_res = supabase.table('carrito_compras').select('id_carrito, estado').eq('cliente_id', cliente_id).execute()
        carritos = getattr(carritos_res, 'data', []) or []
        
        eliminados = []
        
        for carrito in carritos:
            cid = carrito.get('id_carrito')
            estado = carrito.get('estado', '').strip()
            
            # Verificar si tiene productos
            productos = supabase.table('venta').select('producto_id').eq('carrito_id', cid).execute()
            tiene_productos = len(getattr(productos, 'data', []) or []) > 0
            
            # Eliminar si:
            # 1. No tiene productos
            # 2. O estÃ¡ en estado Pendiente (no deberÃ­a tener cliente_id si es pendiente)
            debe_eliminar = False
            razon = ""
            
            if not tiene_productos:
                debe_eliminar = True
                razon = "sin productos"
            elif estado.lower() == 'pendiente':
                debe_eliminar = True
                razon = "estado Pendiente con cliente_id (inconsistente)"
            
            if debe_eliminar:
                try:
                    # El historial de venta no se borra.
                    # Luego eliminar carrito
                    supabase.table('carrito_compras').delete().eq('id_carrito', cid).execute()
                    eliminados.append({'carrito_id': cid, 'razon': razon})
                    print(f"[LIMPIAR_CARRITOS] Eliminado: {cid} ({razon})")
                except Exception as e:
                    print(f"[LIMPIAR_CARRITOS] Error eliminando {cid}: {e}")
        
        print(f"[LIMPIAR_CARRITOS] Total eliminados: {len(eliminados)}")
        
        return jsonify({
            'success': True, 
            'eliminados': len(eliminados),
            'detalles': eliminados
        }), 200
        
    except Exception as e:
        print(f"[LIMPIAR_CARRITOS] Error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@carrito_compras_api.route('/api/admin/resetear_carritos_pendientes', methods=['POST'])
def resetear_carritos_pendientes():
    """
    Admin-only: Resetea carritos en estado Pendiente para remover cliente_id
    Esto es para limpiar carritos que fueron asociados incorrectamente
    """
    try:
        # Obtener todos los carritos en estado Pendiente
        carritos_res = supabase.table('carrito_compras').select('id_carrito').eq('estado', 'Pendiente').execute()
        carritos = getattr(carritos_res, 'data', []) or []
        
        actualizados = []
        for c in carritos:
            cid = c.get('id_carrito')
            try:
                # Resetear cliente_id a NULL para carritos sin pagar
                supabase.table('carrito_compras').update({
                    'cliente_id': None
                }).eq('id_carrito', cid).execute()
                actualizados.append(cid)
                print(f"[RESETEAR] Carrito {cid} - cliente_id resetado a NULL")
            except Exception as e:
                print(f"[RESETEAR] Error en {cid}: {e}")
        
        print(f"[RESETEAR] Total actualizados: {len(actualizados)}")
        
        return jsonify({
            'success': True,
            'actualizados': len(actualizados),
            'carritos': actualizados
        }), 200
        
    except Exception as e:
        print(f"[RESETEAR] Error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

