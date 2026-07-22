# -*- coding: utf-8 -*-
from flask import Blueprint, jsonify, request
from datetime import date, timedelta

from services.supabase_client import supabase

caja_cuadre_bp = Blueprint("caja_cuadre_bp", __name__)

def _normalizar_metodo_pago(raw):
    metodo = " ".join(str(raw or "").strip().lower().split())
    if (
        "tarjeta" in metodo or
        "tajeta" in metodo or
        metodo in {"credito", "debito", "visa", "mastercard", "amex", "diners", "card"}
    ):
        return "tarjeta"
    if "yape" in metodo:
        return "yape"
    if metodo in {"efectivo", "contado", "al contado"}:
        return "contado"
    return ""


def obtener_payload_cuadre_caja(fecha=None):
    fecha = fecha or date.today().isoformat()
    fecha_inicio = date.fromisoformat(fecha)
    fecha_fin = (fecha_inicio + timedelta(days=1)).isoformat()

    # 1. TRAER TODAS LAS VENTAS DEL DÍA CON TIPO_VENTA_ID
    ventas_por_tipo = {}
    totales_por_tipo = {}
    comprobantes = []
    totales = {"tarjeta": 0.0, "contado": 0.0, "yape": 0.0, "total": 0.0}
    
    try:
        result_ventas = (
            supabase.table("venta")
            .select("id_venta, monto, metodo, cliente_id, registro_pago_id, fecha_venta, tipo_venta_id")
            .gte("fecha_venta", fecha)
            .lt("fecha_venta", fecha_fin)
            .order("fecha_venta", desc=True)
            .execute()
        )
        ventas = result_ventas.data or []

        # Agrupar ventas por tipo_venta_id
        for venta in ventas:
            tipo_id = venta.get("tipo_venta_id") or "sin_tipo"
            if tipo_id not in ventas_por_tipo:
                ventas_por_tipo[tipo_id] = []
            ventas_por_tipo[tipo_id].append(venta)

        # Traer tipos de venta
        tipo_venta_ids = [tv_id for tv_id in ventas_por_tipo.keys() if tv_id != "sin_tipo"]
        tipo_venta_map = {}
        if tipo_venta_ids:
            try:
                tipos_res = (
                    supabase.table("tipo_venta")
                    .select("id_tipo, descripcion")
                    .in_("id_tipo", tipo_venta_ids)
                    .execute()
                )
                for tipo in tipos_res.data or []:
                    tipo_venta_map[tipo.get("id_tipo")] = tipo.get("descripcion", "Desconocido")
            except Exception as exc_tipos:  # noqa: BLE001
                print(f"[caja_cuadre] error consultando tipo_venta: {exc_tipos}")

        # Traer comprobantes desde registro_pago
        registro_ids = [row.get("registro_pago_id") for venta_lista in ventas_por_tipo.values() for row in venta_lista if row.get("registro_pago_id")]
        registro_map = {}
        if registro_ids:
            try:
                registros_res = (
                    supabase.table("registro_pago")
                    .select("id_registro, fecha, total, documento")
                    .in_("id_registro", registro_ids)
                    .execute()
                )
                for reg in registros_res.data or []:
                    registro_map[reg.get("id_registro")] = reg
            except Exception as exc_registros:  # noqa: BLE001
                print(f"[caja_cuadre] error consultando registro_pago: {exc_registros}")

        # Traer clientes
        cliente_ids = [row.get("cliente_id") for venta_lista in ventas_por_tipo.values() for row in venta_lista if row.get("cliente_id")]
        cliente_map = {}
        if cliente_ids:
            try:
                clientes_res = (
                    supabase.table("cliente")
                    .select("id_cliente, nombre")
                    .in_("id_cliente", cliente_ids)
                    .execute()
                )
                for cliente in clientes_res.data or []:
                    cliente_map[cliente.get("id_cliente")] = cliente.get("nombre", "-")
            except Exception as exc_clientes:  # noqa: BLE001
                print(f"[caja_cuadre] error consultando clientes: {exc_clientes}")

        # Construir comprobantes y calcular totales por tipo
        for tipo_id, venta_lista in ventas_por_tipo.items():
            tipo_label = tipo_venta_map.get(tipo_id, tipo_id)
            subtotal_tipo = 0.0

            for venta in venta_lista:
                registro = registro_map.get(venta.get("registro_pago_id")) if venta.get("registro_pago_id") else None
                documento = (registro.get("documento") if registro else "") or ""
                monto_venta = float(venta.get("monto") or (registro.get("total") if registro else 0) or 0)

                metodo_raw = venta.get("metodo") or ""
                metodo_norm = _normalizar_metodo_pago(metodo_raw)
                if metodo_norm:
                    totales[metodo_norm] += monto_venta
                totales["total"] += monto_venta
                subtotal_tipo += monto_venta

                cliente_nombre = cliente_map.get(venta.get("cliente_id"), "-")
                metodo_desc = (venta.get("metodo") or "").strip() or "-"
                numero_comprobante = documento or f"VENTA-{str(venta.get('id_venta') or '')[:8]}"
                documento_url = documento if isinstance(documento, str) and documento.startswith("http") else None

                comprobantes.append({
                    "id": venta.get("id_venta"),
                    "numero": numero_comprobante,
                    "cliente": cliente_nombre,
                    "metodo_pago": metodo_desc,
                    "monto": monto_venta,
                    "fecha": venta.get("fecha_venta") or (registro.get("fecha") if registro else "") or "",
                    "documento": documento,
                    "documento_url": documento_url,
                    "comprobante": numero_comprobante,
                    "tipo_venta": tipo_label,
                })

            totales_por_tipo[tipo_label] = round(subtotal_tipo, 2)

    except Exception as exc:  # noqa: BLE001
        print(f"[caja_cuadre] error consultando ventas y comprobantes: {exc}")
        comprobantes = []
        totales = {"tarjeta": 0.0, "contado": 0.0, "yape": 0.0, "total": 0.0}
        totales_por_tipo = {}

    # 2. CANTIDAD EN CAJA: TRAER DE TABLA CAJA SUBTOTAL
    cantidad_en_caja = 0.0
    caja_id_actual = None
    try:
        result_caja = (
            supabase.table("caja")
            .select("id_caja, subtotal")
            .eq("fecha", fecha)
            .neq("turno", "cerrada")  # Excluir cajas cerradas
            .order("id_caja", desc=True)  # Obtener la mas reciente
            .limit(1)
            .execute()
        )
        cajas = result_caja.data or []
        if cajas:
            caja_id_actual = cajas[0].get("id_caja")
            cantidad_en_caja = float(cajas[0].get("subtotal") or 0)
    except Exception as exc:  # noqa: BLE001
        print(f"[caja_cuadre] error consultando caja: {exc}")

    # RETIROS REALIZADOS HOY: desde tabla gastos con tipo='retiro'
    retiros = []
    try:
        result_retiros = (
            supabase.table("gastos")
            .select("id_gasto, monto, fecha, tipo")
            .gte("fecha", fecha)
            .lt("fecha", fecha_fin)
            .ilike("tipo", "%retiro%")
            .order("fecha", desc=True)
            .execute()
        )
        gastos_retiros = result_retiros.data or []
        for g in gastos_retiros:
            retiros.append({
                "id_gasto": g.get("id_gasto"),
                "monto": float(g.get("monto") or 0),
                "fecha": g.get("fecha") or "",
                "tipo": g.get("tipo") or "",
            })
    except Exception as exc:  # noqa: BLE001
        print(f"[caja_cuadre] error consultando retiros: {exc}")

    return {
        "fecha": fecha,
        "totales": totales,
        "totales_por_tipo": totales_por_tipo,
        "comprobantes": comprobantes,
        "cantidad_en_caja": cantidad_en_caja,
        "caja_id": caja_id_actual,
        "retiros": retiros,
    }


@caja_cuadre_bp.route("/api/caja/cuadre", methods=["GET"])
def caja_cuadre():
    fecha = request.args.get("fecha")
    if not fecha:
        fecha = date.today().isoformat()

    return jsonify({
        "success": True,
        **obtener_payload_cuadre_caja(fecha),
    })


@caja_cuadre_bp.route("/api/caja/sumar", methods=["POST"])
def sumar_a_caja():
    """
    Suma un monto al subtotal de la caja activa del dia.
    Se usa al confirmar un pago de servicio.
    """
    try:
        data = request.get_json() or {}
        monto = data.get("monto")
        if not monto or float(monto) <= 0:
            return jsonify({"success": False, "message": "Monto invalido"}), 400

        monto = float(monto)
        fecha_hoy = date.today().isoformat()

        # Buscar caja activa del dia (no cerrada)
        caja_res = (
            supabase.table("caja")
            .select("id_caja, subtotal")
            .eq("fecha", fecha_hoy)
            .neq("turno", "cerrada")
            .order("id_caja", desc=True)
            .limit(1)
            .execute()
        )
        cajas = caja_res.data or []

        if cajas:
            caja_actual = cajas[0]
            nuevo_subtotal = float(caja_actual.get("subtotal") or 0) + monto
            supabase.table("caja").update({
                "subtotal": round(nuevo_subtotal, 2)
            }).eq("id_caja", caja_actual["id_caja"]).execute()
        else:
            # No hay caja abierta hoy, crear una nueva con el monto
            supabase.table("caja").insert({
                "fecha": fecha_hoy,
                "turno": "diurno",
                "subtotal": round(monto, 2)
            }).execute()

        return jsonify({"success": True, "message": "Caja actualizada correctamente"}), 200

    except Exception as exc:
        print(f"[sumar_a_caja] Error: {exc}")
        return jsonify({"success": False, "message": f"Error al actualizar caja: {str(exc)}"}), 500


@caja_cuadre_bp.route("/api/caja/crear-nueva", methods=["POST"])
def crear_nueva_caja():
    """
    Cierra la caja actual del dia y crea una nueva caja con subtotal = 0.
    Este endpoint finaliza la caja actual y prepara para un nuevo turno.
    """
    try:
        fecha_actual = date.today().isoformat()
        data = request.get_json() or {}
        turno = data.get("turno", "diurno")  # Puede ser "diurno", "nocturno", etc.
        
        # 1. Buscar la caja actual del dia
        result_caja_actual = (
            supabase.table("caja")
            .select("id_caja, subtotal")
            .eq("fecha", fecha_actual)
            .execute()
        )
        cajas_actuales = result_caja_actual.data or []
        
        if cajas_actuales:
            # Actualizar turno de la caja actual (marcarla como "cerrada" o cambiar turno)
            caja_anterior = cajas_actuales[0]
            supabase.table("caja").update({
                "turno": "cerrada"  # Marcar como cerrada
            }).eq("id_caja", caja_anterior["id_caja"]).execute()
        
        # 2. Crear nueva caja con subtotal = 0
        nueva_caja = supabase.table("caja").insert({
            "fecha": fecha_actual,
            "turno": turno,
            "subtotal": 0.0
        }).execute()
        
        if nueva_caja.data:
            return jsonify({
                "success": True,
                "message": "Nueva caja creada exitosamente",
                "nueva_caja": nueva_caja.data[0] if nueva_caja.data else {}
            }), 200
        else:
            return jsonify({
                "success": False,
                "message": "Error al crear nueva caja"
            }), 500
            
    except Exception as exc:
        print(f"[crear_nueva_caja] Error: {exc}")
        return jsonify({
            "success": False,
            "message": f"Error al crear nueva caja: {str(exc)}"
        }), 500
