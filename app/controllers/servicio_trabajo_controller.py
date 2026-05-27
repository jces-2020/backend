"""
Controller: Servicio Trabajo
Maneja el workflow de servicios técnicos (REMETRO/RETAZO/PRODUCTOS/INSTALACION).
"""
from flask import Blueprint, jsonify, request
from typing import Optional, Dict, Any
from app.services.supabase_client import supabase
from app.services.venta_service import registrar_venta
import json

servicio_trabajo_bp = Blueprint("servicio_trabajo_bp", __name__)


def _merge_remetro_en_descripcion(descripcion_actual: Any, remetro_data: Dict[str, Any]) -> str:
    """Mezcla los datos de remetro dentro de descripcion como JSON estable."""
    base = {}

    if isinstance(descripcion_actual, dict):
        base = dict(descripcion_actual)
    elif isinstance(descripcion_actual, str) and descripcion_actual.strip():
        try:
            base = json.loads(descripcion_actual)
            if not isinstance(base, dict):
                base = {"detalle": descripcion_actual}
        except Exception:
            base = {"detalle": descripcion_actual}

    base["remetro"] = {
        "ancho": remetro_data.get("remetro_ancho"),
        "alto": remetro_data.get("remetro_alto"),
        "serie": remetro_data.get("remetro_serie"),
        "descripcion": remetro_data.get("remetro_descripcion"),
        "fecha_servicio": remetro_data.get("remetro_fecha_servicio"),
        "ubicacion": remetro_data.get("remetro_ubicacion")
    }
    return json.dumps(base, ensure_ascii=False)


@servicio_trabajo_bp.route("/api/servicio/remetro/guardar", methods=["POST"])
def guardar_remetro():
    """
    POST /api/servicio/remetro/guardar
    Guarda los datos de REMETRO (medidas, serie, descripción, ubicación).
    
    Body: {
        "notificacion_id": uuid,
        "ancho": float,
        "alto": float,
        "serie": str,
        "precio": float,
        "metodo_pago": "por tarjeta" | "al contado" | "por yape",
        "descripcion": str,
        "fecha_servicio": str,
        "ubicacion": str
    }
    """
    try:
        data = request.get_json() or {}
        notificacion_id = data.get("notificacion_id")
        
        precio_raw = data.get("precio")
        metodo_pago = (data.get("metodo_pago") or "").strip().lower()

        # Registrar venta del servicio cuando llega precio válido y método permitido.
        try:
            precio = float(precio_raw)
        except (TypeError, ValueError):
            precio = 0.0

        venta_registrada = False
        metodos_permitidos = {"por tarjeta", "al contado", "por yape"}
        if precio > 0 and metodo_pago in metodos_permitidos:
            venta_ok = registrar_venta(total=precio, metodo=metodo_pago, caja_id=None)
            if not venta_ok:
                print("[SERVICIO] ⚠️ No se pudo registrar la venta del servicio")
                return jsonify({"success": False, "message": "No se pudo registrar la venta del servicio"}), 500
            else:
                venta_registrada = True
                # Cambiar estado de la notificacion a "En proceso" al confirmar el pago
                if notificacion_id:
                    try:
                        estn = supabase.table("estado_notificacion").select("id_estado, descripcion").execute()
                        estado_en_proc_id = None
                        for row in (getattr(estn, "data", None) or []):
                            desc = (row.get("descripcion") or "").strip().upper()
                            if desc in ("EN PROCESO", "EN_PROCESO"):
                                estado_en_proc_id = row.get("id_estado")
                                break
                        if estado_en_proc_id:
                            supabase.table("notificacion") \
                                .update({"estado_notificacion_id": estado_en_proc_id}) \
                                .eq("id_notificacion", notificacion_id) \
                                .execute()
                            print(f"[SERVICIO] ✅ Notificacion {notificacion_id} marcada En proceso")
                        else:
                            print("[SERVICIO] ⚠️ No se encontro estado 'En proceso' en BD")
                    except Exception as est_err:
                        print(f"[SERVICIO] ⚠️ No se pudo actualizar estado notificacion: {est_err}")
        elif precio > 0:
            print(f"[SERVICIO] ⚠️ Método de pago inválido para venta: '{metodo_pago}'")
            return jsonify({"success": False, "message": "Metodo de pago invalido"}), 400
        else:
            print("[SERVICIO] ⚠️ Precio inválido o no enviado; no se registró venta")
            return jsonify({"success": False, "message": "Precio invalido"}), 400

        # Guardar datos de REMETRO de forma opcional (no debe bloquear el flujo ni la venta)
        remetro_data = {
            "remetro_ancho": data.get("ancho"),
            "remetro_alto": data.get("alto"),
            "remetro_serie": data.get("serie"),
            "remetro_descripcion": data.get("descripcion"),
            "remetro_fecha_servicio": data.get("fecha_servicio"),
            "remetro_ubicacion": data.get("ubicacion")
        }

        servicios_actualizados = data.get("servicios_actualizados") or []
        presupuestos_actualizados = 0

        if isinstance(servicios_actualizados, list):
            for item in servicios_actualizados:
                if not isinstance(item, dict):
                    continue

                id_presupuesto = item.get("id_presupuesto")
                if not id_presupuesto:
                    continue

                update_data = {}

                if item.get("ancho") is not None:
                    try:
                        update_data["ancho"] = float(item.get("ancho"))
                    except (TypeError, ValueError):
                        pass
                if item.get("alto") is not None:
                    try:
                        update_data["alto"] = float(item.get("alto"))
                    except (TypeError, ValueError):
                        pass
                if item.get("descripcion") is not None:
                    update_data["descripcion"] = str(item.get("descripcion")).strip()

                if not update_data:
                    continue

                try:
                    res_update = supabase.table("presupuesto") \
                        .update(update_data) \
                        .eq("id_presupuesto", id_presupuesto) \
                        .execute()
                    err_update = getattr(res_update, 'error', None) if res_update is not None else None
                    if err_update:
                        print(f"[SERVICIO] ⚠️ Error actualizando presupuesto {id_presupuesto}: {err_update}")
                    else:
                        presupuestos_actualizados += 1
                except Exception as pres_err:
                    print(f"[SERVICIO] ⚠️ Excepción actualizando presupuesto {id_presupuesto}: {pres_err}")

        remetro_guardado = False
        if notificacion_id:
            print(f"[SERVICIO] Guardando REMETRO para notificación {notificacion_id}: {remetro_data}")
            try:
                resultado = supabase.table("notificacion") \
                    .update(remetro_data) \
                    .eq("id_notificacion", notificacion_id) \
                    .execute()

                err = getattr(resultado, 'error', None) if resultado is not None else None
                if err:
                    # Si las columnas remetro_* no existen aún, no bloquear el flujo de venta.
                    codigo = err.get("code") if isinstance(err, dict) else None
                    if codigo == "PGRST204":
                        print(f"[SERVICIO] ⚠️ Columnas REMETRO no existen en notificacion. Guardando fallback en descripcion: {err}")

                        notif_actual = supabase.table("notificacion") \
                            .select("descripcion") \
                            .eq("id_notificacion", notificacion_id) \
                            .limit(1) \
                            .execute()
                        actual_data = (getattr(notif_actual, "data", None) or [{}])[0]
                        descripcion_actual = (actual_data or {}).get("descripcion")
                        descripcion_merge = _merge_remetro_en_descripcion(descripcion_actual, remetro_data)

                        fallback_resultado = supabase.table("notificacion") \
                            .update({"descripcion": descripcion_merge}) \
                            .eq("id_notificacion", notificacion_id) \
                            .execute()

                        fallback_err = getattr(fallback_resultado, 'error', None) if fallback_resultado is not None else None
                        if fallback_err:
                            print(f"[SERVICIO] ⚠️ Error guardando fallback REMETRO en descripcion: {fallback_err}")
                        else:
                            remetro_guardado = True
                    else:
                        print(f"[SERVICIO] ⚠️ Error actualizando REMETRO (no bloqueante): {err}")
                else:
                    remetro_guardado = True
            except Exception as rem_err:
                print(f"[SERVICIO] ⚠️ Excepción guardando REMETRO (no bloqueante): {rem_err}")
        else:
            print("[SERVICIO] ⚠️ notificacion_id no enviado; se omite actualización de REMETRO")
        
        print(f"[SERVICIO] ✅ REMETRO guardado exitosamente")
        return jsonify({
            "success": True,
            "message": "Datos procesados correctamente",
            "remetro_guardado": remetro_guardado,
            "venta_registrada": venta_registrada,
            "presupuestos_actualizados": presupuestos_actualizados
        }), 200
        
    except Exception as e:
        print(f"[SERVICIO] ❌ Error: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500


@servicio_trabajo_bp.route("/api/servicio/remetro/<notificacion_id>", methods=["GET"])
def obtener_remetro_guardado(notificacion_id: str):
    """
    GET /api/servicio/remetro/<notificacion_id>
    Devuelve datos de remetro guardados para precargar formulario.
    """
    try:
        if not notificacion_id:
            return jsonify({"success": False, "message": "notificacion_id requerido"}), 400

        row = {}
        try:
            resultado = supabase.table("notificacion") \
                .select("descripcion, remetro_ancho, remetro_alto, remetro_serie, remetro_descripcion, remetro_fecha_servicio, remetro_ubicacion") \
                .eq("id_notificacion", notificacion_id) \
                .limit(1) \
                .execute()
            row = ((getattr(resultado, "data", None) or [{}])[0]) if resultado is not None else {}
        except Exception:
            # Fallback seguro cuando aún no existen columnas remetro_* en la tabla.
            only_desc = supabase.table("notificacion") \
                .select("descripcion") \
                .eq("id_notificacion", notificacion_id) \
                .limit(1) \
                .execute()
            row = ((getattr(only_desc, "data", None) or [{}])[0]) if only_desc is not None else {}

        descripcion_raw = row.get("descripcion")
        descripcion_json = {}
        if isinstance(descripcion_raw, dict):
            descripcion_json = descripcion_raw
        elif isinstance(descripcion_raw, str) and descripcion_raw.strip():
            try:
                parsed = json.loads(descripcion_raw)
                if isinstance(parsed, dict):
                    descripcion_json = parsed
            except Exception:
                descripcion_json = {}

        remetro_fallback = descripcion_json.get("remetro") if isinstance(descripcion_json.get("remetro"), dict) else {}

        data = {
            "ancho": row.get("remetro_ancho") if row.get("remetro_ancho") is not None else remetro_fallback.get("ancho"),
            "alto": row.get("remetro_alto") if row.get("remetro_alto") is not None else remetro_fallback.get("alto"),
            "serie": row.get("remetro_serie") if row.get("remetro_serie") is not None else remetro_fallback.get("serie"),
            "descripcion": row.get("remetro_descripcion") if row.get("remetro_descripcion") is not None else remetro_fallback.get("descripcion"),
            "fecha_servicio": row.get("remetro_fecha_servicio") if row.get("remetro_fecha_servicio") is not None else remetro_fallback.get("fecha_servicio"),
            "ubicacion": row.get("remetro_ubicacion") if row.get("remetro_ubicacion") is not None else remetro_fallback.get("ubicacion")
        }

        return jsonify({"success": True, "data": data}), 200
    except Exception as e:
        print(f"[SERVICIO] ❌ Error obteniendo REMETRO: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500


@servicio_trabajo_bp.route("/api/servicio/instalacion/guardar", methods=["POST"])
def guardar_instalacion():
    """
    POST /api/servicio/instalacion/guardar
    Guarda los datos de INSTALACION (fecha, técnico, observaciones).
    
    Body: {
        "notificacion_id": uuid,
        "fecha_instalacion": str,
        "tecnico_asignado": str,
        "observaciones": str,
        "cantidad_imagenes": int
    }
    """
    try:
        data = request.get_json() or {}
        notificacion_id = data.get("notificacion_id")
        
        if not notificacion_id:
            return jsonify({"success": False, "message": "notificacion_id requerido"}), 400
        
        # Preparar datos de INSTALACION
        instalacion_data = {
            "instalacion_fecha": data.get("fecha_instalacion"),
            "instalacion_tecnico": data.get("tecnico_asignado"),
            "instalacion_observaciones": data.get("observaciones"),
            "instalacion_cantidad_imagenes": data.get("cantidad_imagenes", 0)
        }
        
        print(f"[SERVICIO] Guardando INSTALACION para notificación {notificacion_id}: {instalacion_data}")
        
        # Actualizar la notificación con los datos de INSTALACION
        resultado = supabase.table("notificacion") \
            .update(instalacion_data) \
            .eq("id_notificacion", notificacion_id) \
            .execute()
        
        err = getattr(resultado, 'error', None) if resultado is not None else None
        if err:
            print(f"[SERVICIO] Error actualizando notificación: {err}")
            return jsonify({"success": False, "message": str(err)}), 500
        
        print(f"[SERVICIO] ✅ INSTALACION guardada exitosamente")
        return jsonify({
            "success": True,
            "message": "Datos de INSTALACION guardados correctamente"
        }), 200
        
    except Exception as e:
        print(f"[SERVICIO] ❌ Error: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500


@servicio_trabajo_bp.route("/productos/disponibles", methods=["GET"])
def get_productos_disponibles():
    """
    Obtiene la lista de productos disponibles para selección.
    Query params:
    - busqueda: str (opcional)
    - tipo: REMETRO | RETAZO | PRODUCTOS
    """
    try:
        busqueda = request.args.get("busqueda", "")
        tipo = request.args.get("tipo", "PRODUCTOS")
        
        # TODO: Implementar búsqueda de productos
        # productos = buscar_productos_disponibles(busqueda, tipo)
        
        return jsonify({
            "success": True,
            "data": [],
            "message": "Endpoint en desarrollo"
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@servicio_trabajo_bp.route("/guardar", methods=["POST"])
def guardar_servicio():
    """
    Guarda los datos del servicio técnico.
    Body: {
        "cliente": str,
        "fecha": str,
        "productos_seleccionados": [],
        "barras": [],
        "cortes": [],
        "instalacion": { "fecha": str, "tecnico": str, "observaciones": str, "imagenes": [] }
    }
    """
    try:
        data = request.get_json()
        
        cliente = data.get("cliente")
        if not cliente:
            return jsonify({"success": False, "message": "Cliente requerido"}), 400
        
        # TODO: Implementar guardado
        # resultado = guardar_servicio_trabajo(data)
        
        return jsonify({
            "success": True,
            "message": "Servicio guardado correctamente"
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@servicio_trabajo_bp.route("/<servicio_id>", methods=["GET"])
def get_servicio_detalle(servicio_id: str):
    """
    Obtiene el detalle de un servicio específico.
    """
    try:
        # TODO: Obtener detalle del servicio
        # servicio = get_servicio_by_id(servicio_id)
        
        return jsonify({
            "success": True,
            "data": {},
            "message": "Endpoint en desarrollo"
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@servicio_trabajo_bp.route("/<servicio_id>/instalacion", methods=["PATCH"])
def update_instalacion(servicio_id: str):
    """
    Actualiza los datos de instalación del servicio.
    """
    try:
        data = request.get_json()
        
        # TODO: Actualizar instalación
        # resultado = actualizar_instalacion(servicio_id, data)
        
        return jsonify({
            "success": True,
            "message": "Instalación actualizada"
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
