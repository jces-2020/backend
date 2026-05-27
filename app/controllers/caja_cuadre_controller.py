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

    # COMPROBANTES: de registro_pago con cliente
    comprobantes = []
    try:
        # Intentar primero con columnas extendidas; si no existen, usar un select basico.
        try:
            result_comprobantes = (
                supabase.table("registro_pago")
                .select("id_registro, fecha, monto, documento, metodo_pago, cliente_id, metodo_pago_id")
                .gte("fecha", fecha)
                .lt("fecha", fecha_fin)
                .order("fecha", desc=True)
                .execute()
            )
        except Exception:
            result_comprobantes = (
                supabase.table("registro_pago")
                .select("id_registro, fecha, monto, documento, cliente_id")
                .gte("fecha", fecha)
                .lt("fecha", fecha_fin)
                .order("fecha", desc=True)
                .execute()
            )
        registros = result_comprobantes.data or []
        documentos_vistos = set()

        cliente_ids = list({r.get("cliente_id") for r in registros if r.get("cliente_id")})
        cliente_map = {}
        if cliente_ids:
            clientes_res = (
                supabase.table("cliente")
                .select("id_cliente, nombre")
                
                .in_("id_cliente", cliente_ids)
                .execute()
            )
            for cliente in clientes_res.data or []:
                cliente_map[cliente.get("id_cliente")] = cliente.get("nombre", "-")

        # Si hay fila con comprobante PDF y otra sin documento para mismo cliente/fecha/monto,
        # priorizar la fila con documento para evitar duplicados visuales.
        firmas_con_documento = set()
        for r in registros:
            doc = str(r.get("documento") or "").strip()
            if doc:
                firma = (
                    str(r.get("cliente_id") or ""),
                    str(r.get("fecha") or "")[:10],
                    round(float(r.get("monto") or 0), 2),
                )
                firmas_con_documento.add(firma)

        for r in registros:
            documento = r.get("documento") or ""
            if documento and documento in documentos_vistos:
                continue

            if not documento:
                firma = (
                    str(r.get("cliente_id") or ""),
                    str(r.get("fecha") or "")[:10],
                    round(float(r.get("monto") or 0), 2),
                )
                if firma in firmas_con_documento:
                    continue

            if documento:
                documentos_vistos.add(documento)

            # Obtener nombre del cliente
            cliente_nombre = cliente_map.get(r.get("cliente_id"), "-")

            # Obtener descripción del método: preferir valor directo
            metodo_desc = ""
            metodo_directo = r.get("metodo_pago")
            if isinstance(metodo_directo, str) and metodo_directo.strip():
                metodo_desc = metodo_directo.strip()
            else:
                metodo_desc = ""

            monto = float(r.get("monto") or 0)
            numero_comprobante = documento or str(r.get("id_registro") or "")[:8]
            documento_url = documento if isinstance(documento, str) and documento.startswith("http") else None

            comprobantes.append({
                "id": r.get("id_registro"),
                "numero": numero_comprobante,
                "cliente": cliente_nombre,
                "metodo_pago": metodo_desc or "-",
                "monto": monto,
                "fecha": r.get("fecha") or "",
                "documento": documento,
                "documento_url": documento_url,
                "comprobante": numero_comprobante,
            })
    except Exception as exc:  # noqa: BLE001
        print(f"[caja_cuadre] error consultando comprobantes de registro_pago: {exc}")
        comprobantes = []

    # TOTALES: de venta por método
    totales = {"tarjeta": 0.0, "contado": 0.0, "yape": 0.0, "total": 0.0}
    try:
        result_ventas = (
            supabase.table("venta")
            .select("metodo, total")
            .gte("fecha_venta", fecha)
            .lt("fecha_venta", fecha_fin)
            .execute()
        )
        ventas = result_ventas.data or []

        for v in ventas:
            metodo_raw = v.get("metodo") or ""
            total = float(v.get("total") or 0)

            metodo_norm = _normalizar_metodo_pago(metodo_raw)
            if metodo_norm:
                totales[metodo_norm] += total
            totales["total"] += total

    except Exception as exc:  # noqa: BLE001
        print(f"[caja_cuadre] error consultando ventas: {exc}")

    cantidad_en_caja = 0.0
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
        "comprobantes": comprobantes,
        "cantidad_en_caja": cantidad_en_caja,
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
