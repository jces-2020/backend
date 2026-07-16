from flask import Blueprint, jsonify, request
from app.services.supabase_client import supabase
from app.services.cortes_service import calcular_total_corte, es_material_aluminio
from app.services.venta_detalle_service import (
    obtener_carrito_ids_por_cliente,
    obtener_cliente_id_por_carrito,
    obtener_detalle_venta_por_carrito,
)
import os, json, base64, hmac, hashlib, time, re, threading

pedidos_detalle_api = Blueprint('pedidos_detalle_api', __name__)
bp = pedidos_detalle_api  # alias para auto-registro del factory
DEBUG_AUTH_LOGS = os.environ.get('DEBUG_AUTH_LOGS', '').strip().lower() in ('1', 'true', 'yes', 'si')

# ─── IN-MEMORY LOCK (mecanismo primario anti-concurrencia) ────────────────────
# Clave: notif_id  Valor: {"worker_id": str, "worker_name": str, "at": float}
# Protegido por threading.Lock para garantizar atomicidad entre hilos.
_notif_locks: dict = {}
_notif_lock_mutex = threading.Lock()


def _dbg(msg: str):
    if DEBUG_AUTH_LOGS:
        print(msg)

# ─── JWT (HS256 sin dependencia externa) ───────────────────────────────────────

def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode('utf-8')

def _b64url_decode(data: str) -> bytes:
    rem = len(data) % 4
    if rem:
        data += '=' * (4 - rem)
    return base64.urlsafe_b64decode(data)

def verify_jwt(token: str):
    try:
        parts = token.split('.')
        _dbg(f"[DEBUG verify_jwt] Token partes: {len(parts)}")
        if len(parts) != 3:
            return None
        header  = json.loads(_b64url_decode(parts[0]).decode('utf-8'))
        payload = json.loads(_b64url_decode(parts[1]).decode('utf-8'))
        signature = parts[2]
        if header.get('alg') != 'HS256':
            return None
        secret = os.environ.get('JWT_SECRET', 'devsecret-change-me')
        signing_input = parts[0] + '.' + parts[1]
        expected = hmac.new(secret.encode('utf-8'), signing_input.encode('utf-8'), hashlib.sha256).digest()
        expected_b64 = _b64url(expected)
        if not hmac.compare_digest(signature, expected_b64):
            return None
        if payload.get('exp') and int(payload['exp']) < int(time.time()):
            return None
        return payload
    except Exception as e:
        import traceback
        _dbg(f"[DEBUG verify_jwt] Excepción: {e}\n{traceback.format_exc()}")
        return None


def _require_personal(request, allowed_areas=None):
    auth = request.headers.get('Authorization', '')
    if not auth.startswith('Bearer '):
        return False, (jsonify({'success': False, 'message': 'No autorizado'}), 401)
    token = auth.split(' ', 1)[1]
    payload = verify_jwt(token)
    if not payload or payload.get('aud') != 'personal':
        return False, (jsonify({'success': False, 'message': 'Token inválido'}), 401)
    if allowed_areas:
        area = (payload.get('area') or '').upper()
        area = area.replace('Ã', 'A').replace('É', 'E').replace('Í', 'I').replace('Ó', 'O').replace('Ú', 'U')
        if area == 'OPERACIONES':
            area = 'OBRAS'
        allowed_norm = [
            a.upper().replace('Ã', 'A').replace('É', 'E').replace('Í', 'I').replace('Ó', 'O').replace('Ú', 'U')
            for a in allowed_areas
        ]
        if area not in allowed_norm:
            return False, (jsonify({'success': False, 'message': 'Área no autorizada'}), 403)
    return True, payload


# ─── HELPER: parsear descripción de notificación ──────────────────────────────

UUID_RE = r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}'

def _parse_notif_desc(desc_str: str):
    """
    Extrae metadatos (especialmente carrito_id) del campo descripcion.

    Casos que maneja:
      1. JSON válido  → devuelve el dict directamente.
      2. Texto plano con patrón explícito "Carrito: <uuid>" o "carrito_id: <uuid>"
         → captura ESE uuid (no el primero del texto, que suele ser el ID del pago).
         Ejemplo: "Pago a3c510b1-... - items: 2 (Carrito: c0fbd034-...)"
      3. Fallback: si hay exactamente 1 UUID en el texto lo usa como carrito_id.
         Si hay 2 o más sin etiqueta no asume nada (devuelve {}).
    """
    if not desc_str:
        return {}

    # Si ya viene como objeto JSON desde Supabase, usarlo directo.
    if isinstance(desc_str, dict):
        return dict(desc_str)

    # Evitar errores cuando llega un tipo distinto a str.
    if not isinstance(desc_str, str):
        desc_str = str(desc_str)

    # 1. JSON ──────────────────────────────────────────────────────────────────
    stripped = desc_str.strip()
    if stripped.startswith('{'):
        try:
            data = json.loads(stripped)
            if isinstance(data, dict):
                return data
        except Exception:
            pass

    out = {}

    # 2. Patrón explícito "Carrito: <uuid>" ───────────────────────────────────
    #    Cubre:  Carrito: xxx  |  carrito_id: xxx  |  (Carrito: xxx)
    m = re.search(
        r'(?:carrito(?:_id)?)\s*[:\-]\s*(' + UUID_RE + r')',
        desc_str,
        re.IGNORECASE
    )
    if m:
        out['carrito_id'] = m.group(1)
        # Intentar extraer cantidad  "items: N"
        qty = re.search(r'items?\s*[:\-]\s*(\d+)', desc_str, re.IGNORECASE)
        if qty:
            out['cantidad'] = int(qty.group(1))
        return out

    # 3. Fallback: exactamente 1 UUID en el texto ─────────────────────────────
    all_uuids = re.findall(UUID_RE, desc_str)
    if len(all_uuids) == 1:
        out['carrito_id'] = all_uuids[0]

    # 2+ UUIDs sin etiqueta → no asumir cuál es el carrito
    return out


def _infer_tipo_notif(item: dict) -> str:
    try:
        desc = str(item.get('descripcion_raw') or '').lower()
    except Exception:
        desc = ''
    estado = str(item.get('carrito_estado') or '').strip().lower()
    if 'optim' in desc:
        return 'OPTIMIZACION'
    if estado in ('listo', 'pagado'):
        return 'ENTREGA'
    return 'SERVICIO'


def _to_float(value, default=0.0):
    """Convierte números tolerando None, strings vacíos y coma decimal."""
    try:
        if value is None:
            return float(default)
        if isinstance(value, str):
            v = value.strip()
            if not v:
                return float(default)
            return float(v.replace(',', '.'))
        return float(value)
    except Exception:
        return float(default)


def _obtener_mapa_productos(producto_ids):
    ids = [pid for pid in (producto_ids or []) if pid]
    if not ids:
        return {}
    try:
        productos = supabase.table('productos').select('*').in_('id_producto', ids).execute().data or []
    except Exception:
        productos = []
    return {p.get('id_producto'): p for p in productos}


def _construir_items_detalle(carrito_id):
    return obtener_detalle_venta_por_carrito(carrito_id)


# ─── RUTAS ────────────────────────────────────────────────────────────────────

@pedidos_detalle_api.route('/api/admin/notificaciones', methods=['GET'])
def listar_notificaciones_admin():
    """Lista notificaciones de trabajo para el panel (requiere JWT de personal)."""
    try:
        ok, resp = _require_personal(request, allowed_areas=['ALMACEN', 'ADMINISTRACION', 'OBRAS', 'TRABAJO'])
        if not ok:
            return resp

        ocultar_atendidas = (request.args.get('ocultar_atendidas') or '').strip().lower() in ('1', 'true', 'yes', 'si')
        tipo_filter = (request.args.get('tipo') or '').strip().upper()

        res = supabase.table('notificacion').select('*').execute()
        notifs_raw = getattr(res, 'data', []) or []
        notifs_raw.sort(key=lambda n: n.get('fecha') or '', reverse=True)

        # Cache de estados de notificación
        estados_map = {}
        try:
            estn = supabase.table('estado_notificacion').select('id_estado, descripcion').execute()
            for row in getattr(estn, 'data', []) or []:
                estados_map[row.get('id_estado')] = (row.get('descripcion') or '').strip()
        except Exception:
            estados_map = {}

        notifs = []
        tipos_habilitados = {'SERVICIO', 'ENTREGA'}

        # Evita N+1 queries: primero parsear y luego resolver estados de carrito en lote.
        parsed_rows = []
        carrito_ids = []
        seen_carritos = set()
        for n in notifs_raw:
            meta = _parse_notif_desc(n.get('descripcion'))
            carrito_id = meta.get('carrito_id')
            parsed_rows.append((n, meta, carrito_id))
            carrito_key = str(carrito_id or '').strip()
            if carrito_key and carrito_key not in seen_carritos:
                seen_carritos.add(carrito_key)
                carrito_ids.append(carrito_key)

        carrito_estado_map = {}
        if carrito_ids:
            try:
                carritos = supabase.table('carrito_compras').select('id_carrito, estado').in_('id_carrito', carrito_ids).execute()
                for row in getattr(carritos, 'data', []) or []:
                    cid = str(row.get('id_carrito') or '').strip()
                    if not cid:
                        continue
                    carrito_estado_map[cid] = (row.get('estado') or '').strip() or None
            except Exception:
                carrito_estado_map = {}

        for n, meta, carrito_id in parsed_rows:
            c_estado = carrito_estado_map.get(str(carrito_id or '').strip())

            desc_txt = meta.get('texto') or n.get('descripcion') or ''
            if meta.get('cantidad'):
                desc_txt = f"Cantidad de productos a llevar: {meta.get('cantidad')}"

            item = {
                'id':                    n.get('id_notificacion') or n.get('id'),
                'nombre':                n.get('nombre'),
                'id_cliente':            n.get('id_cliente'),
                'cliente_id':            n.get('id_cliente'),
                'cantidad':              meta.get('cantidad'),
                'carrito_id':            carrito_id,
                'descripcion_raw':       n.get('descripcion'),
                'descripcion':           desc_txt,
                'estado_notificacion_id': n.get('estado_notificacion_id'),
                'carrito_estado':        c_estado,
                'estado_label':          estados_map.get(n.get('estado_notificacion_id')),
                'en_proceso_por_id':     meta.get('en_proceso_por_id'),
                'en_proceso_por_nombre': meta.get('en_proceso_por_nombre'),
                'en_proceso_at':         meta.get('en_proceso_at'),
                'fecha':                 n.get('fecha') or n.get('created_at'),
            }

            item_tipo = (n.get('tipo') or '').strip().upper()
            if not item_tipo:
                item_tipo = _infer_tipo_notif(item)
            item['tipo'] = item_tipo

            if item_tipo not in tipos_habilitados:
                continue

            if ocultar_atendidas and (str(item.get('carrito_estado') or '').lower() in ('listo', 'pagado')):
                continue

            if tipo_filter and item_tipo != tipo_filter:
                continue

            notifs.append(item)

        return jsonify({'success': True, 'notificaciones': notifs}), 200

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


def _get_estado_id_por_nombre(nombre: str):
    """Mapea nombre de estado a id_estado."""
    try:
        estn = supabase.table('estado_notificacion').select('id_estado, descripcion').execute()
        nombre_n = (nombre or '').strip().upper()
        mapeo = {
            'EN_PROCESO':  'EN PROCESO',
            'FINALIZANDO': 'FINALIZANDO',
            'ATENDIDA':    'ATENDIDA',
            'PENDIENTE':   'PENDIENTE',
        }
        nombre_mapped = mapeo.get(nombre_n, nombre_n)
        for row in getattr(estn, 'data', []) or []:
            desc = (row.get('descripcion') or '').strip().upper()
            if desc == nombre_mapped or desc == nombre_n:
                return row.get('id_estado')
        return None
    except Exception:
        return None


def _get_estado_desc_por_id(estado_id: str):
    """Obtiene la descripción del estado_notificacion por id_estado."""
    try:
        if not estado_id:
            return None
        estn = supabase.table('estado_notificacion').select('id_estado, descripcion').execute()
        for row in getattr(estn, 'data', []) or []:
            if str(row.get('id_estado')) == str(estado_id):
                return (row.get('descripcion') or '').strip()
        return None
    except Exception:
        return None


@pedidos_detalle_api.route("/api/admin/notificaciones/<notif_id>/estado", methods=["PATCH", "POST"])
def actualizar_estado_notificacion_admin(notif_id):
    """Actualiza el estado de trabajo de una notificacion."""
    import traceback as _tb
    print(f"[ESTADO] Recibida peticion para notif={notif_id} method={request.method}")
    try:
        ok, auth_payload = _require_personal(request, allowed_areas=["ALMACEN", "ADMINISTRACION", "OBRAS", "TRABAJO"])
        if not ok:
            return auth_payload

        data = request.get_json(silent=True) or {}
        estado_req = (data.get("estado") or "").strip().upper()
        print(f"[ESTADO] estado_req={estado_req} notif={notif_id}")

        if estado_req not in ("EN_PROCESO", "FINALIZANDO", "ATENDIDA"):
            return jsonify({"success": False, "message": "Estado invalido"}), 400

        eid = _get_estado_id_por_nombre(estado_req)
        print(f"[ESTADO] eid={eid} para {estado_req}")
        if not eid:
            return jsonify({"success": False, "message": "Estado no configurado en BD"}), 400

        nres = supabase.table("notificacion").select("id_notificacion,estado_notificacion_id,descripcion,venta_id,nombre").eq("id_notificacion", notif_id).limit(1).execute()
        notif_data = None
        if nres and getattr(nres, "data", None):
            notif_data = nres.data[0]
        if not notif_data:
            return jsonify({"success": False, "message": "Notificacion no encontrada"}), 404

        raw_desc = notif_data.get("descripcion")
        meta = _parse_notif_desc(raw_desc)
        if isinstance(raw_desc, str):
            raw_desc_clean = raw_desc.strip()
            if raw_desc_clean and not raw_desc_clean.startswith('{'):
                meta.setdefault("texto", raw_desc_clean)
        worker_id = str(auth_payload.get("sub") or "")
        worker_name = (auth_payload.get("name") or "").strip()
        locked_by_id = str(meta.get("en_proceso_por_id") or "")
        locked_by_name = (meta.get("en_proceso_por_nombre") or "").strip()

        # ── LOCK PRIMARIO: in-memory, atomico por threading.Lock ─────────────
        # Se evalua ANTES de cualquier llamada a la BD. Garantiza que dentro del
        # mismo proceso solo UN trabajador puede reclamar la notificacion.
        if estado_req == "EN_PROCESO":
            with _notif_lock_mutex:
                mem = _notif_locks.get(notif_id)
                print(f"[LOCK] notif={notif_id} mem={mem} worker={worker_id}")
                if mem and mem.get("worker_id") and mem["worker_id"] != worker_id:
                    return jsonify({
                        "success": False,
                        "message": "Esta notificacion ya esta en proceso por otro trabajador",
                        "locked_by": {"id": mem["worker_id"], "name": mem.get("worker_name") or "Otro trabajador"}
                    }), 409
                # Reclamar el lock en memoria
                _notif_locks[notif_id] = {"worker_id": worker_id, "worker_name": worker_name}
        elif estado_req in ("FINALIZANDO", "ATENDIDA"):
            with _notif_lock_mutex:
                mem = _notif_locks.get(notif_id)
                if mem and mem.get("worker_id") == worker_id:
                    del _notif_locks[notif_id]

        # ── LOCK SECUNDARIO: verificar en BD (cubre multi-proceso / reinicio) ─
        # Solo bloquea si el DB tiene un dueno distinto confirmado.
        if estado_req == "EN_PROCESO":
            if locked_by_id and worker_id and locked_by_id != worker_id:
                # Otro proceso ya registro el lock en BD: revertir el in-memory
                with _notif_lock_mutex:
                    _notif_locks.pop(notif_id, None)
                return jsonify({
                    "success": False,
                    "message": "Esta notificacion ya esta en proceso por otro trabajador",
                    "locked_by": {"id": locked_by_id, "name": locked_by_name or "Otro trabajador"}
                }), 409

        if estado_req == "EN_PROCESO":
            # Preservar carrito_id si no estaba en la descripcion original
            if not meta.get("carrito_id"):
                try:
                        venta_id = notif_data.get("venta_id")
                        if venta_id:
                            vres = supabase.table("venta").select("carrito_id").eq("id_venta", venta_id).limit(1).execute()
                            if getattr(vres, "data", None):
                                meta["carrito_id"] = vres.data[0].get("carrito_id") or ""
                except Exception as _ce:
                    print(f"[WARN] No se pudo recuperar carrito_id para lock: {_ce}")
            if worker_id:
                meta["en_proceso_por_id"] = worker_id
            if worker_name:
                meta["en_proceso_por_nombre"] = worker_name
            if not meta.get("en_proceso_at"):
                meta["en_proceso_at"] = int(time.time())
        elif estado_req in ("FINALIZANDO", "ATENDIDA"):
            meta.pop("en_proceso_por_id", None)
            meta.pop("en_proceso_por_nombre", None)
            meta.pop("en_proceso_at", None)

        # ── Actualizar estado_notificacion_id (SIEMPRE debe funcionar) ──
        print(f"[ESTADO] Actualizando notif={notif_id} estado_id={eid} lock_id={meta.get('en_proceso_por_id','')}")

        # ── Update atómico: estado + descripcion en UNA SOLA llamada ──────────
        # Intentamos dict primero (JSONB), luego json.dumps (TEXT), luego solo estado
        _actualizado = False
        for _desc_val in [meta, json.dumps(meta, ensure_ascii=False)]:
            try:
                supabase.table("notificacion").update({
                    "estado_notificacion_id": eid,
                    "descripcion": _desc_val,
                }).eq("id_notificacion", notif_id).execute()
                _actualizado = True
                print(f"[ESTADO] Update OK (desc={'dict' if isinstance(_desc_val,dict) else 'str'}) lock_id={meta.get('en_proceso_por_id','')}")
                break
            except Exception as _e:
                print(f"[ESTADO] Update fallo con desc={'dict' if isinstance(_desc_val,dict) else 'str'}: {_e}")
        if not _actualizado:
            # Último recurso: al menos actualizar el estado
            supabase.table("notificacion").update({
                "estado_notificacion_id": eid,
            }).eq("id_notificacion", notif_id).execute()
            print(f"[WARN] Solo estado_id actualizado para notif={notif_id} — lock data NO guardada")

        # ── Verify-after-write: re-leer BD para detectar race conditions ──────
        # Si dos workers escribieron al mismo tiempo, solo el ultimo es el dueno.
        # El que no es dueno recibe 409 aqui aunque su UPDATE haya "funcionado".
        if estado_req == "EN_PROCESO" and worker_id and _actualizado:
            try:
                vres = supabase.table("notificacion").select("descripcion") \
                    .eq("id_notificacion", notif_id).limit(1).execute()
                if vres.data:
                    vmeta = _parse_notif_desc(vres.data[0].get("descripcion"))
                    real_lock = str(vmeta.get("en_proceso_por_id") or "")
                    if real_lock and real_lock != worker_id:
                        print(f"[LOCK] Race condition detectada: actual={real_lock} solicitante={worker_id}")
                        return jsonify({
                            "success": False,
                            "message": "Esta notificacion fue tomada por otro trabajador al mismo tiempo",
                            "locked_by": {"id": real_lock, "name": vmeta.get("en_proceso_por_nombre") or "Otro trabajador"}
                        }), 409
            except Exception as ve:
                print(f"[WARN] Verify-after-write fallo: {ve}")  # no bloquear si falla la verificacion

        # Actualizar el carrito vinculado a ESTA notificacion
        _estado_carrito_map = {
            "EN_PROCESO":  "en proceso",
            "FINALIZANDO": "listo",
            "ATENDIDA":    "entregado",
        }
        nuevo_estado_carrito = _estado_carrito_map.get(estado_req)
        if nuevo_estado_carrito:
            try:
                carrito_id = meta.get("carrito_id") or _parse_notif_desc(raw_desc).get("carrito_id")
                print(f"[ESTADO] carrito_id={carrito_id} nuevo_estado={nuevo_estado_carrito}")
                if carrito_id:
                    supabase.table("carrito_compras").update({"estado": nuevo_estado_carrito}).eq("id_carrito", carrito_id).execute()
                    print(f"[ESTADO] Carrito {carrito_id} actualizado a '{nuevo_estado_carrito}' OK")
                else:
                    print(f"[WARN] Sin carrito_id en notif {notif_id} — no se actualiza carrito")
            except Exception as ce:
                print(f"[WARN] No se pudo actualizar carrito para notif {notif_id}: {ce}")

        return jsonify({"success": True, "estado": estado_req}), 200

    except Exception as e:
        print(f"[ERROR] actualizar_estado_notificacion_admin {notif_id}: {e}\n{_tb.format_exc()}")
        return jsonify({"success": False, "error": str(e)}), 500


@pedidos_detalle_api.route('/api/admin/notificaciones/<notif_id>/detalle', methods=['GET'])
def detalle_notificacion_admin(notif_id):
    """Devuelve el detalle del pedido asociado a la notificación."""
    try:
        ok, resp = _require_personal(request, allowed_areas=['ALMACEN', 'ADMINISTRACION', 'OBRAS', 'TRABAJO'])
        if not ok:
            return resp

        nres = supabase.table('notificacion').select('*').eq('id_notificacion', notif_id).limit(1).execute()
        if not nres or not getattr(nres, 'data', None):
            return jsonify({'success': False, 'message': 'Notificación no encontrada'}), 404

        notif = nres.data[0]
        meta = _parse_notif_desc(notif.get('descripcion'))
        carrito_id = meta.get('carrito_id')

        if not carrito_id:
            return jsonify({'success': False, 'message': 'No se pudo determinar el carrito asociado'}), 400

        car = supabase.table('carrito_compras').select('*').eq('id_carrito', carrito_id).limit(1).execute()
        if not car or not getattr(car, 'data', None):
            return jsonify({'success': False, 'message': 'Pedido no encontrado'}), 404

        carrito = car.data[0]
        pedido_meta = {
            'id':         carrito.get('id_carrito'),
            'estado':     carrito.get('estado') or 'Proceso',
            'created_at': carrito.get('created_at') or carrito.get('fecha'),
        }

        # Cliente
        cliente = None
        cliente_id = obtener_cliente_id_por_carrito(carrito_id)
        if cliente_id:
            cli = supabase.table('cliente').select('*').eq('id_cliente', cliente_id).limit(1).execute()
            if cli and cli.data:
                row = cli.data[0]
                cliente = {
                    'id':             row.get('id_cliente'),
                    'nombre':         row.get('nombre'),
                    'numero':         row.get('numero') or row.get('telefono') or row.get('celular'),
                    'tipo_documento': row.get('tipo_documento') or row.get('tipo_doc'),
                    'documento':      row.get('documento') or row.get('dni') or row.get('ruc'),
                    'correo':         row.get('correo') or row.get('email'),
                }

        joined, total_items, total_precio = _construir_items_detalle(carrito_id)

        return jsonify({
            'success': True,
            'notificacion': {
                'id':       notif.get('id_notificacion') or notif.get('id'),
                'nombre':   notif.get('nombre'),
                'cantidad': meta.get('cantidad'),
            },
            'pedido':       pedido_meta,
            'cliente':      cliente,
            'items':        joined,
            'total_items':  total_items,
            'total_precio': round(total_precio, 2),
        }), 200

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@pedidos_detalle_api.route('/api/admin/pedidos/buscar', methods=['GET'])
def buscar_pedidos_por_cliente_admin():
    """Busca pedidos por documento, número o correo del cliente."""
    try:
        ok, resp = _require_personal(request, allowed_areas=['ALMACEN', 'ADMINISTRACION', 'OBRAS', 'TRABAJO'])
        if not ok:
            return resp

        documento = request.args.get('documento')
        numero    = request.args.get('numero')
        correo    = request.args.get('correo')
        if not (documento or numero or correo):
            return jsonify({'success': False, 'message': 'Provee documento, numero o correo'}), 400

        cli_res = None
        if documento:
            cli_res = supabase.table('cliente').select('*').eq('documento', documento).limit(1).execute()
        elif numero:
            cli_res = supabase.table('cliente').select('*').eq('numero', numero).limit(1).execute()
        elif correo:
            cli_res = supabase.table('cliente').select('*').eq('correo', correo).limit(1).execute()

        if not cli_res or not getattr(cli_res, 'data', None):
            return jsonify({'success': True, 'cliente': None, 'pedidos': []}), 200

        cli = cli_res.data[0]
        cid = cli.get('id_cliente')

        carrito_ids = obtener_carrito_ids_por_cliente(cid)
        carritos = []
        if carrito_ids:
            res = supabase.table('carrito_compras').select('*').in_('id_carrito', carrito_ids).execute()
            carritos = res.data or []
        pedidos  = []
        for c in carritos:
            pedidos.append({
                'id':         c.get('id_carrito'),
                'estado':     c.get('estado') or 'Proceso',
                'created_at': c.get('created_at') or c.get('fecha'),
            })
        pedidos.sort(key=lambda x: x.get('created_at') or '', reverse=True)

        cliente = {
            'id':             cid,
            'nombre':         cli.get('nombre'),
            'numero':         cli.get('numero'),
            'documento':      cli.get('documento'),
            'tipo_documento': cli.get('tipo_documento') or cli.get('tipo_doc'),
            'correo':         cli.get('correo'),
        }
        return jsonify({'success': True, 'cliente': cliente, 'pedidos': pedidos}), 200

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@pedidos_detalle_api.route('/api/admin/pedidos/<carrito_id>/detalle', methods=['GET'])
def obtener_detalle_pedido_admin(carrito_id):
    """Devuelve el detalle completo de un pedido para el panel de Almacén/Obras."""
    try:
        ok, resp = _require_personal(request, allowed_areas=['ALMACEN', 'ADMINISTRACION', 'OBRAS', 'TRABAJO'])
        if not ok:
            return resp

        # Carrito
        car = supabase.table('carrito_compras').select('*').eq('id_carrito', carrito_id).limit(1).execute()
        if not car or not getattr(car, 'data', None):
            return jsonify({'success': False, 'message': 'Pedido no encontrado'}), 404

        carrito = car.data[0]
        pedido_meta = {
            'id':         carrito.get('id_carrito'),
            'estado':     carrito.get('estado') or 'Proceso',
            'created_at': carrito.get('created_at') or carrito.get('fecha'),
        }

        # Cliente
        cliente_row = None
        cliente_id = obtener_cliente_id_por_carrito(carrito_id)
        if cliente_id:
            try:
                cli = supabase.table('cliente').select('*').eq('id_cliente', cliente_id).limit(1).execute()
                if cli and cli.data:
                    cliente_row = cli.data[0]
            except Exception:
                cliente_row = None

        cliente = None
        if cliente_row:
            cliente = {
                'id':             cliente_row.get('id_cliente'),
                'nombre':         cliente_row.get('nombre'),
                'numero':         cliente_row.get('numero') or cliente_row.get('telefono') or cliente_row.get('celular'),
                'tipo_documento': cliente_row.get('tipo_documento') or cliente_row.get('tipo_doc'),
                'documento':      cliente_row.get('documento') or cliente_row.get('dni') or cliente_row.get('ruc'),
                'correo':         cliente_row.get('correo') or cliente_row.get('email'),
            }
        else:
            # Fallback: buscar nombre desde notificación
            try:
                nres = supabase.table('notificacion').select('nombre, descripcion').execute()
                notif_nombre = None
                if nres and getattr(nres, 'data', None):
                    for n in nres.data:
                        meta = _parse_notif_desc(n.get('descripcion'))
                        if str(meta.get('carrito_id')) == str(carrito_id):
                            notif_nombre = n.get('nombre')
                            break
                if notif_nombre:
                    busc = supabase.table('cliente').select('*').eq('nombre', notif_nombre).limit(2).execute()
                    if busc and getattr(busc, 'data', None):
                        if len(busc.data) == 1:
                            r = busc.data[0]
                            cliente = {
                                'id':             r.get('id_cliente'),
                                'nombre':         r.get('nombre'),
                                'numero':         r.get('numero') or r.get('telefono') or r.get('celular'),
                                'tipo_documento': r.get('tipo_documento') or r.get('tipo_doc'),
                                'documento':      r.get('documento') or r.get('dni') or r.get('ruc'),
                                'correo':         r.get('correo') or r.get('email'),
                            }
                        else:
                            cliente = {'id': None, 'nombre': notif_nombre, 'numero': None,
                                       'tipo_documento': None, 'documento': None, 'correo': None}
            except Exception:
                pass

        joined, total_items, total_precio = _construir_items_detalle(carrito_id)
        if not joined:
            return jsonify({
                'success': True, 'pedido': pedido_meta, 'cliente': cliente,
                'items': [], 'total_items': 0, 'total_precio': 0.0,
            }), 200

        return jsonify({
            'success':      True,
            'pedido':       pedido_meta,
            'cliente':      cliente,
            'items':        joined,
            'total_items':  total_items,
            'total_precio': round(total_precio, 2),
        }), 200

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@pedidos_detalle_api.route('/api/admin/backfill/asociar-clientes', methods=['POST'])
def backfill_asociar_clientes():
    """Asocia carrito_compras.cliente_id usando el nombre de notificacion (backfill)."""
    try:
        ok, resp = _require_personal(request, allowed_areas=['ALMACEN', 'ADMINISTRACION', 'OBRAS', 'TRABAJO'])
        if not ok:
            return resp

        dry_run = False
        try:
            q = request.args.get('dry_run')
            if q is not None:
                dry_run = str(q).strip().lower() in ('1', 'true', 'yes', 'si')
            else:
                body = request.get_json(silent=True) or {}
                if isinstance(body, dict):
                    v = body.get('dry_run')
                    if isinstance(v, bool):
                        dry_run = v
                    elif isinstance(v, str):
                        dry_run = v.strip().lower() in ('1', 'true', 'yes', 'si')
        except Exception:
            pass

        res    = supabase.table('notificacion').select('id_notificacion, nombre, descripcion, venta_id').execute()
        notifs = getattr(res, 'data', []) or []

        summary = {
            'updated': 0, 'skipped_no_carrito': 0, 'skipped_tiene_cliente': 0,
            'skipped_nombre_generico': 0, 'skipped_sin_coincidencia': 0,
            'skipped_multiples_coincidencias': 0, 'errors': 0,
        }
        details = []

        for n in notifs:
            try:
                meta       = _parse_notif_desc(n.get('descripcion'))
                carrito_id = meta.get('carrito_id')
                if not carrito_id:
                    summary['skipped_no_carrito'] += 1
                    details.append({'carrito_id': None, 'notif_nombre': n.get('nombre'), 'action': 'skip:no_carrito'})
                    continue

                car = supabase.table('carrito_compras').select('id_carrito').eq('id_carrito', carrito_id).limit(1).execute()
                if not car or not getattr(car, 'data', None):
                    summary['skipped_no_carrito'] += 1
                    details.append({'carrito_id': carrito_id, 'notif_nombre': n.get('nombre'), 'action': 'skip:carrito_no_existe'})
                    continue

                # El esquema nuevo no asocia cliente al carrito; el vínculo vive en venta.

                notif_nombre = (n.get('nombre') or '').strip()
                if notif_nombre.lower() in ('', 'cliente'):
                    summary['skipped_nombre_generico'] += 1
                    details.append({'carrito_id': carrito_id, 'notif_nombre': notif_nombre, 'action': 'skip:nombre_generico'})
                    continue

                busc = supabase.table('cliente').select('id_cliente, nombre').eq('nombre', notif_nombre).execute()
                rows = getattr(busc, 'data', []) or []
                if len(rows) == 0:
                    summary['skipped_sin_coincidencia'] += 1
                    details.append({'carrito_id': carrito_id, 'notif_nombre': notif_nombre, 'action': 'skip:sin_coincidencia'})
                    continue
                if len(rows) > 1:
                    summary['skipped_multiples_coincidencias'] += 1
                    details.append({'carrito_id': carrito_id, 'notif_nombre': notif_nombre, 'action': 'skip:multiples_coincidencias'})
                    continue

                matched = rows[0]
                if dry_run:
                    summary['updated'] += 1
                    details.append({'carrito_id': carrito_id, 'notif_nombre': notif_nombre,
                                    'matched_cliente_id': matched.get('id_cliente'), 'action': 'would_update'})
                else:
                        # El vínculo cliente<->carrito ya no se persiste en carrito_compras.
                        summary['skipped_tiene_cliente'] += 1
                        details.append({'carrito_id': carrito_id, 'notif_nombre': notif_nombre,
                                        'matched_cliente_id': matched.get('id_cliente'), 'action': 'skip:no_carrito_cliente'})
            except Exception as ex:
                summary['errors'] += 1
                details.append({'carrito_id': meta.get('carrito_id') if 'meta' in locals() else None,
                                 'notif_nombre': n.get('nombre'), 'action': 'error', 'reason': str(ex)})

        return jsonify({'success': True, 'dry_run': dry_run, 'summary': summary, 'details': details}), 200

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@pedidos_detalle_api.route('/api/admin/pedidos/<carrito_id>', methods=['DELETE'])
def eliminar_pedido_admin(carrito_id):
    """Elimina un pedido (carrito), sus items y notificaciones asociadas."""
    try:
        ok, auth_payload = _require_personal(request, allowed_areas=['ALMACEN', 'ADMINISTRACION', 'OBRAS', 'TRABAJO'])
        if not ok:
            return auth_payload

        worker_id = str(auth_payload.get('sub') or '')

        # Verificar si existe una notificación asociada en proceso por otro trabajador
        try:
            n_all = supabase.table('notificacion').select('id_notificacion, descripcion, estado_notificacion_id').execute()
            estado_en_proceso = None
            try:
                estn = supabase.table('estado_notificacion').select('id_estado, descripcion').execute()
                for row in getattr(estn, 'data', []) or []:
                    if (row.get('descripcion') or '').strip().upper() == 'EN PROCESO':
                        estado_en_proceso = row.get('id_estado')
                        break
            except Exception:
                estado_en_proceso = None

            for row in getattr(n_all, 'data', []) or []:
                meta = _parse_notif_desc(row.get('descripcion'))
                if str(meta.get('carrito_id')) != str(carrito_id):
                    continue
                locked_by_id = str(meta.get('en_proceso_por_id') or '')
                locked_by_name = meta.get('en_proceso_por_nombre') or ''

                # Consultar in-memory lock (tiene prioridad)
                notif_id_row = str(row.get('id_notificacion') or '')
                with _notif_lock_mutex:
                    mem = _notif_locks.get(notif_id_row)
                mem_owner = mem.get('worker_id') if mem else None
                mem_name  = mem.get('worker_name') if mem else ''

                is_in_process = False
                if estado_en_proceso and str(row.get('estado_notificacion_id')) == str(estado_en_proceso):
                    is_in_process = True
                elif locked_by_id or mem_owner:
                    is_in_process = True

                if is_in_process:
                    # In-memory tiene prioridad sobre BD
                    if mem_owner:
                        effective_owner = mem_owner
                        effective_name  = mem_name or locked_by_name or 'otro trabajador'
                    elif locked_by_id:
                        effective_owner = locked_by_id
                        effective_name  = locked_by_name or 'otro trabajador'
                    else:
                        effective_owner = ''
                        effective_name  = 'otro trabajador'

                    if not effective_owner:
                        # Lock fantasma: estado EN_PROCESO pero sin dueno identificado. Permitir.
                        break
                    if effective_owner != worker_id:
                        return jsonify({'success': False,
                            'message': f'No puedes eliminar este pedido porque ya esta en proceso por {effective_name}',
                            'locked_by': {'name': effective_name}}), 409
                    # effective_owner == worker_id → mismo trabajador, permitir
        except Exception:
            pass

        deleted_items    = 0
        deleted_carritos = 0
        deleted_notifs   = 0

        # 1) Ítems: ya no se elimina venta; el historial debe permanecer.
        deleted_items = 0

        # 2) Carrito
        try:
            car_del = supabase.table('carrito_compras').delete().eq('id_carrito', carrito_id).execute()
            if getattr(car_del, 'data', None):
                deleted_carritos = len(car_del.data)
        except Exception:
            deleted_carritos = 0

        # 3) Notificaciones asociadas
        try:
            try:
                n_like = supabase.table('notificacion').select('id_notificacion, descripcion') \
                    .like('descripcion', f"%{carrito_id}%").execute()
                ids = [row.get('id_notificacion') for row in getattr(n_like, 'data', []) or [] if row.get('id_notificacion')]
            except Exception:
                n_all = supabase.table('notificacion').select('id_notificacion, descripcion').execute()
                ids = []
                for row in getattr(n_all, 'data', []) or []:
                    meta = _parse_notif_desc(row.get('descripcion'))
                    if str(meta.get('carrito_id')) == str(carrito_id):
                        ids.append(row.get('id_notificacion'))

            for nid in ids:
                try:
                    supabase.table('notificacion').delete().eq('id_notificacion', nid).execute()
                    deleted_notifs += 1
                except Exception:
                    pass
        except Exception:
            deleted_notifs = 0

        return jsonify({
            'success':          True,
            'deleted_items':    deleted_items,
            'deleted_carritos': deleted_carritos,
            'deleted_notifs':   deleted_notifs,
        }), 200

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@pedidos_detalle_api.route('/api/admin/notificaciones/<notif_id>', methods=['DELETE'])
def eliminar_notificacion_admin(notif_id):
    """Elimina una notificación de servicio y limpia su carrito/cortes asociados si existen."""
    try:
        ok, auth_payload = _require_personal(request, allowed_areas=['ALMACEN', 'ADMINISTRACION', 'OBRAS', 'TRABAJO'])
        if not ok:
            return auth_payload

        worker_id = str(auth_payload.get('sub') or '')

        nres = supabase.table('notificacion').select('*').eq('id_notificacion', notif_id).limit(1).execute()
        notif = (getattr(nres, 'data', None) or [None])[0]
        if not notif:
            return jsonify({'success': False, 'message': 'Notificación no encontrada'}), 404

        meta = _parse_notif_desc(notif.get('descripcion'))
        locked_by_id = str(meta.get('en_proceso_por_id') or '')
        locked_by_name = meta.get('en_proceso_por_nombre') or 'otro trabajador'

        # Verificar in-memory lock ademas de BD
        with _notif_lock_mutex:
            mem = _notif_locks.get(notif_id)
        mem_owner = mem.get("worker_id") if mem else None

        estado_actual_desc = (_get_estado_desc_por_id(notif.get('estado_notificacion_id')) or '').strip().upper()
        in_process = estado_actual_desc in ('EN PROCESO', 'EN_PROCESO') or bool(locked_by_id) or bool(mem_owner)
        if in_process:
            # In-memory lock tiene prioridad (igual que el endpoint de estado)
            # Si el in-memory dice que el trabajador actual es el dueno, se permite
            if mem_owner:
                effective_owner = mem_owner
                effective_name = (mem.get("worker_name") or '') if mem else 'otro trabajador'
            elif locked_by_id:
                effective_owner = locked_by_id
                effective_name = locked_by_name
            else:
                effective_owner = ""
                effective_name = "otro trabajador"
            if not effective_owner:
                # Lock fantasma: estado EN_PROCESO pero sin dueno identificado. Permitir.
                pass
            elif effective_owner != worker_id:
                return jsonify({
                    'success': False,
                    'message': f'No puedes eliminar este servicio porque ya esta en proceso por {effective_name}',
                    'locked_by': {'name': effective_name}
                }), 409

        carrito_id = meta.get('carrito_id')

        if not carrito_id and (str(notif.get('tipo') or '').strip().upper() == 'SERVICIO'):
            try:
                cortes_res = supabase.table('cortes').select('id_corte, carrito_id, normbre').eq('normbre', notif.get('nombre')).execute()
                carrito_ids = list({str(c.get('carrito_id')) for c in (getattr(cortes_res, 'data', None) or []) if c.get('carrito_id')})
                if len(carrito_ids) == 1:
                    carrito_id = carrito_ids[0]
            except Exception:
                carrito_id = None

        deleted_cortes = 0
        deleted_items = 0
        deleted_carritos = 0

        if carrito_id:
            try:
                cortes_del = supabase.table('cortes').delete().eq('carrito_id', carrito_id).execute()
                deleted_cortes = len(getattr(cortes_del, 'data', None) or [])
            except Exception:
                deleted_cortes = 0

            # En el nuevo esquema no se borra la venta asociada.
            deleted_items = 0

            try:
                car_del = supabase.table('carrito_compras').delete().eq('id_carrito', carrito_id).execute()
                deleted_carritos = len(getattr(car_del, 'data', None) or [])
            except Exception:
                deleted_carritos = 0

        supabase.table('notificacion').delete().eq('id_notificacion', notif_id).execute()

        # Limpiar lock en memoria al eliminar
        with _notif_lock_mutex:
            _notif_locks.pop(notif_id, None)

        return jsonify({
            'success': True,
            'message': 'Servicio eliminado correctamente',
            'deleted_cortes': deleted_cortes,
            'deleted_items': deleted_items,
            'deleted_carritos': deleted_carritos,
            'carrito_id': carrito_id,
        }), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500