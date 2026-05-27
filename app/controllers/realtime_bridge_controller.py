# -*- coding: utf-8 -*-
"""
Bridge de eventos realtime via SSE.
Emite eventos cuando detecta cambios en Supabase para:
- notificacion/estado_notificacion (panel OBRAS)
- productos.cantidad (stock)
- servicios (catalogo de proyectos)
- mermas (retazos)
"""

import json
import re
import time
from datetime import date
from flask import Blueprint, Response, stream_with_context
from app.services.supabase_client import supabase, SUPABASE_URL
from controllers.caja_cuadre_controller import obtener_payload_cuadre_caja

realtime_bridge_bp = Blueprint("realtime_bridge", __name__)


_UUID_RE = re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")


def _parse_notif_desc(desc):
    if isinstance(desc, dict):
        meta = dict(desc)
        raw = json.dumps(meta, ensure_ascii=False)
    else:
        raw = (str(desc) if desc is not None else "").strip()
        meta = {}

    try:
        loaded = json.loads(raw)
        if isinstance(loaded, dict):
            meta.update(loaded)
    except Exception:
        pass

    if "carrito_id" not in meta:
        m = _UUID_RE.search(raw)
        if m:
            meta["carrito_id"] = m.group(0)

    if "cantidad" not in meta:
        m2 = re.search(r"items?:\s*(\d+)", raw, flags=re.IGNORECASE)
        if m2:
            try:
                meta["cantidad"] = int(m2.group(1))
            except Exception:
                pass

    return meta


def _infer_tipo_notif(item):
    t = (item.get("tipo") or "").strip().upper()
    if t in ("ENTREGA", "SERVICIO"):
        return t
    try:
        desc = str(item.get("descripcion") or "").lower()
    except Exception:
        desc = ""
    estado = str(item.get("carrito_estado") or "").strip().lower()
    if "optim" in desc:
        return "OPTIMIZACION"
    if estado in ("listo", "pagado"):
        return "ENTREGA"
    return "SERVICIO"


def _load_notificaciones_snapshot():
    snapshot = {}

    try:
        res = supabase.table("notificacion").select("*").execute()
        notifs_raw = res.data or []
    except Exception:
        return snapshot

    estados_map = {}
    try:
        estn = supabase.table("estado_notificacion").select("id_estado, descripcion").execute()
        for row in (estn.data or []):
            estados_map[row.get("id_estado")] = (row.get("descripcion") or "").strip()
    except Exception:
        estados_map = {}

    carrito_ids = []
    parsed = []
    for n in notifs_raw:
        meta = _parse_notif_desc(n.get("descripcion"))
        carrito_id = meta.get("carrito_id")
        if carrito_id:
            carrito_ids.append(carrito_id)
        parsed.append((n, meta, carrito_id))

    carrito_map = {}
    try:
        if carrito_ids:
            cres = supabase.table("carrito_compras").select("id_carrito, estado").in_("id_carrito", carrito_ids).execute()
            for c in (cres.data or []):
                carrito_map[c.get("id_carrito")] = (c.get("estado") or "").strip()
    except Exception:
        carrito_map = {}

    for n, meta, carrito_id in parsed:
        desc_txt = meta.get("texto") or n.get("descripcion") or ""
        if meta.get("cantidad") is not None:
            desc_txt = f"Cantidad de productos a llevar: {meta.get('cantidad')}"

        item = {
            "id": n.get("id_notificacion") or n.get("id"),
            "id_notificacion": n.get("id_notificacion") or n.get("id"),
            "nombre": n.get("nombre"),
            "id_cliente": n.get("id_cliente"),
            "cliente_id": n.get("id_cliente"),
            "cantidad": meta.get("cantidad"),
            "carrito_id": carrito_id,
            "descripcion": desc_txt,
            "descripcion_raw": n.get("descripcion"),
            "estado_notificacion_id": n.get("estado_notificacion_id"),
            "carrito_estado": carrito_map.get(carrito_id),
            "estado_label": estados_map.get(n.get("estado_notificacion_id")),
            "en_proceso_por_id": meta.get("en_proceso_por_id"),
            "en_proceso_por_nombre": meta.get("en_proceso_por_nombre"),
            "en_proceso_at": meta.get("en_proceso_at"),
            "fecha": n.get("fecha") or n.get("created_at"),
            "tipo": (n.get("tipo") or "").strip().upper(),
        }
        item["tipo"] = _infer_tipo_notif(item)

        item_id = str(item.get("id") or "")
        if item_id:
            snapshot[item_id] = item

    return snapshot


def _load_productos_snapshot():
    snapshot = {}
    max_retries = 3
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            prod_res = supabase.table("productos").select(
                "id_producto, codigo, nombre, cantidad, precio_unitario, descripcion, grosor, "
                "categoria_id, almacen_id, stock_id, IMG_P, categoria:categoria_id(descripcion), "
                "almacen:almacen_id(fila, columna)"
            ).execute()
            
            for p in (prod_res.data or []):
                pid = str(p.get("id_producto") or "")
                if not pid:
                    continue
                
                # Construir objeto producto completo igual a como lo hace el controller
                categoria_nombre = None
                if 'categoria' in p and isinstance(p['categoria'], dict):
                    categoria_nombre = p['categoria'].get('descripcion')
                
                img_url = p.get('IMG_P') or ""
                if img_url and not img_url.startswith('http'):
                    img_url = f"{SUPABASE_URL}/storage/v1/object/public/IMG/PRODUCTOS/{img_url}"
                
                snapshot[pid] = {
                    'id_producto': pid,
                    'codigo': p.get('codigo'),
                    'nombre': p.get('nombre'),
                    'cantidad': p.get('cantidad', 0),
                    'precio_unitario': p.get('precio_unitario'),
                    'descripcion': p.get('descripcion'),
                    'grosor': p.get('grosor'),
                    'categoria_id': p.get('categoria_id'),
                    'almacen_id': p.get('almacen_id'),
                    'stock_id': p.get('stock_id'),
                    'IMG_P': img_url,
                    'categoria': categoria_nombre,
                    'fila': p.get('almacen', {}).get('fila') if isinstance(p.get('almacen'), dict) else None,
                    'columna': p.get('almacen', {}).get('columna') if isinstance(p.get('almacen'), dict) else None
                }
            return snapshot
            
        except Exception as e:
            retry_count += 1
            if retry_count >= max_retries:
                print(f"[ERROR] _load_productos_snapshot despues de {max_retries} intentos: {e}")
                return snapshot
            else:
                print(f"[WARN] _load_productos_snapshot (intento {retry_count}/{max_retries}): {e}")
                time.sleep(0.5 * retry_count)  # Espera progresiva: 0.5s, 1s, 1.5s
    
    return snapshot


def _build_servicio_public_url(item):
    ing = item.get("ING")
    if not ing:
        return None
    try:
        if str(ing).startswith("http"):
            return ing
        return supabase.storage.from_("IMG").get_public_url(ing)
    except Exception:
        return None


def _load_servicios_snapshot():
    snapshot = {}
    max_retries = 3
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            # Orden descendente para que lo mas nuevo aparezca primero.
            sres = supabase.table("servicio").select("*").order("id_servicio", desc=True).execute()
            for raw in (sres.data or []):
                sid = str(raw.get("id_servicio") or raw.get("id") or "")
                if not sid:
                    continue

                row = dict(raw)
                row["id_servicio"] = raw.get("id_servicio") or raw.get("id")
                row["nombre"] = raw.get("nombre") or raw.get("nombre_servicio") or raw.get("titulo") or "Servicio"
                row["descripcion"] = raw.get("descripcion") or raw.get("detalle") or ""
                row["imagen_public_url"] = _build_servicio_public_url(raw)
                snapshot[sid] = row
            return snapshot
            
        except Exception as e:
            retry_count += 1
            if retry_count >= max_retries:
                print(f"[ERROR] _load_servicios_snapshot despues de {max_retries} intentos: {e}")
                return snapshot
            else:
                print(f"[WARN] _load_servicios_snapshot (intento {retry_count}/{max_retries}): {e}")
                time.sleep(0.5 * retry_count)
    
    return snapshot


def _load_mermas_snapshot():
    snapshot = {}
    max_retries = 3
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            res = supabase.table("merma").select(
                "id_merma, id_categoria, ancho_cm, alto_cm, lugar, nombre, cantidad, descripci\u00f3n, fecha_registro, area"
            ).execute()
            for row in (res.data or []):
                mid = str(row.get("id_merma") or "")
                if not mid:
                    continue
                snapshot[mid] = dict(row)
            return snapshot
            
        except Exception as e:
            retry_count += 1
            if retry_count >= max_retries:
                print(f"[ERROR] _load_mermas_snapshot despues de {max_retries} intentos: {e}")
                return snapshot
            else:
                print(f"[WARN] _load_mermas_snapshot (intento {retry_count}/{max_retries}): {e}")
                time.sleep(0.5 * retry_count)
    
    return snapshot


def _load_caja_snapshot():
    snapshot = {}
    try:
        payload = obtener_payload_cuadre_caja(date.today().isoformat())
        snapshot["cuadre_hoy"] = payload
    except Exception as e:
        print(f"[WARN] _load_caja_snapshot: {e}")
    return snapshot


def _compute_changes(prev_snapshot, curr_snapshot):
    changes = []

    prev_ids = set(prev_snapshot.keys())
    curr_ids = set(curr_snapshot.keys())

    inserted = curr_ids - prev_ids
    deleted = prev_ids - curr_ids
    common = prev_ids & curr_ids

    for _id in inserted:
        changes.append({"op": "insert", "id": _id, "record": curr_snapshot[_id]})

    for _id in deleted:
        changes.append({"op": "delete", "id": _id, "record": None})

    for _id in common:
        if prev_snapshot[_id] != curr_snapshot[_id]:
            changes.append({"op": "update", "id": _id, "record": curr_snapshot[_id]})

    return changes


def _sse_stream(kind: str):
    if kind == "notificaciones":
        snapshot_fn = _load_notificaciones_snapshot
        event_name = "notificaciones_changed"
    elif kind == "productos":
        snapshot_fn = _load_productos_snapshot
        event_name = "productos_changed"
    elif kind == "caja":
        snapshot_fn = _load_caja_snapshot
        event_name = "caja_changed"
    elif kind == "mermas":
        snapshot_fn = _load_mermas_snapshot
        event_name = "mermas_changed"
    else:
        snapshot_fn = _load_servicios_snapshot
        event_name = "servicios_changed"

    last_snapshot = snapshot_fn()
    last_heartbeat = time.time()
    consecutive_errors = 0
    max_consecutive_errors = 10

    # Evento inicial para sincronizar estado al abrir conexion
    init_payload = {
        "kind": kind,
        "ts": int(time.time() * 1000),
        "initial": True,
        "changes": [{"op": "snapshot", "id": k, "record": v} for k, v in last_snapshot.items()],
    }
    yield f"event: {event_name}\n"
    yield f"data: {json.dumps(init_payload, ensure_ascii=False)}\n\n"

    while True:
        # Ajustar sleep segun errores consecutivos
        base_sleep = 0.9
        error_multiplier = min(1 + (consecutive_errors * 0.5), 5)  # Max 5.9 segundos
        sleep_time = base_sleep * error_multiplier
        time.sleep(sleep_time)

        try:
            current_snapshot = snapshot_fn()
            
            # Si la snapshot no esta vacia, resetear contador de errores
            if current_snapshot:
                consecutive_errors = 0
            
            changes = _compute_changes(last_snapshot, current_snapshot)
            if changes:
                last_snapshot = current_snapshot
                payload = {
                    "kind": kind,
                    "ts": int(time.time() * 1000),
                    "initial": False,
                    "changes": changes,
                }
                yield f"event: {event_name}\n"
                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

        except Exception as e:
            consecutive_errors += 1
            print(f"[WARN] SSE stream {kind} (error #{consecutive_errors}): {e}")
            
            if consecutive_errors >= max_consecutive_errors:
                print(f"[ERROR] Demasiados errores consecutivos en {kind}. Cerrando stream.")
                break
            continue

        now = time.time()
        if now - last_heartbeat >= 15:
            last_heartbeat = now
            heartbeat = {"kind": kind, "ts": int(now * 1000), "heartbeat": True}
            yield "event: heartbeat\n"
            yield f"data: {json.dumps(heartbeat)}\n\n"


@realtime_bridge_bp.route("/api/realtime/notificaciones", methods=["GET"])
def stream_notificaciones():
    return Response(
        stream_with_context(_sse_stream("notificaciones")),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@realtime_bridge_bp.route("/api/realtime/productos", methods=["GET"])
def stream_productos():
    return Response(
        stream_with_context(_sse_stream("productos")),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@realtime_bridge_bp.route("/api/realtime/servicios", methods=["GET"])
def stream_servicios():
    return Response(
        stream_with_context(_sse_stream("servicios")),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@realtime_bridge_bp.route("/api/realtime/mermas", methods=["GET"])
def stream_mermas():
    return Response(
        stream_with_context(_sse_stream("mermas")),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@realtime_bridge_bp.route("/api/realtime/caja", methods=["GET"])
def stream_caja():
    return Response(
        stream_with_context(_sse_stream("caja")),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
