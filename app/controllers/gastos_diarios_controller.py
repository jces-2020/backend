from flask import Blueprint, jsonify, request
from datetime import date

from services.gastos_service import (
    get_gastos_by_date,
    get_caja_by_date,
    get_ventas_by_date,
    create_gasto,
    get_resumen_dia
)
from services.pago_balance_service import restar_monto_empresa

gastos_diarios_bp = Blueprint("gastos_diarios_bp", __name__)


@gastos_diarios_bp.route("/api/gastos-diarios", methods=["GET"])
def list_gastos():
    """Lista los gastos de una fecha específica (hoy por defecto)."""
    fecha = request.args.get("fecha", str(date.today()))
    gastos = get_gastos_by_date(fecha)
    return jsonify({"success": True, "data": gastos, "fecha": fecha})


@gastos_diarios_bp.route("/api/gastos-diarios", methods=["POST"])
def add_gasto():
    """Crea un nuevo gasto."""
    data = request.get_json() or {}
    monto = data.get("monto")
    fecha_gasto = data.get("fecha") or str(date.today())
    caja_id = data.get("caja_id")
    tipo = (data.get("tipo") or "").strip()
    
    if monto is None:
        return jsonify({"success": False, "message": "Monto requerido"}), 400

    if not tipo:
        return jsonify({"success": False, "message": "Tipo requerido"}), 400

    try:
        monto_float = float(monto)
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "Monto invalido"}), 400

    if monto_float <= 0:
        return jsonify({"success": False, "message": "Monto debe ser mayor a 0"}), 400
    
    gasto = create_gasto(monto_float, fecha_gasto, caja_id, tipo)
    if not gasto:
        return jsonify({"success": False, "message": "Error al registrar gasto"}), 500

    # Descontar el gasto del saldo acumulado de empresa en tabla pago.
    try:
        saldo_actualizado = restar_monto_empresa(monto_float)
    except Exception as exc:
        # Revertir gasto si falla actualización de saldo para evitar inconsistencia.
        try:
            if gasto.get("id_gasto"):
                from services.supabase_client import supabase
                supabase.table("gastos").delete().eq("id_gasto", gasto["id_gasto"]).execute()
        except Exception as rollback_exc:
            print(f"[add_gasto] Error en rollback de gasto: {rollback_exc}")
        print(f"[add_gasto] Error actualizando saldo empresa: {exc}")
        return jsonify({"success": False, "message": "No se pudo actualizar saldo en tabla pago"}), 500

    return jsonify({
        "success": True,
        "message": "Gasto registrado",
        "data": {
            "gasto": gasto,
            "saldo_empresa": saldo_actualizado,
        },
    })


@gastos_diarios_bp.route("/api/caja", methods=["GET"])
def list_caja():
    """Lista las cajas de una fecha específica."""
    fecha = request.args.get("fecha", str(date.today()))
    cajas = get_caja_by_date(fecha)
    return jsonify({"success": True, "data": cajas, "fecha": fecha})


@gastos_diarios_bp.route("/api/gastos-diarios/resumen", methods=["GET"])
def resumen_gastos():
    """Obtiene un resumen completo de gastos e ingresos del día."""
    fecha = request.args.get("fecha", str(date.today()))
    resumen = get_resumen_dia(fecha)
    return jsonify({"success": True, "data": resumen})


@gastos_diarios_bp.route("/api/caja/retiro", methods=["POST"])
def registrar_retiro():
    """Registra un retiro de caja como gasto tipo 'Retiro' y actualiza el subtotal de la caja asociada."""
    data = request.get_json() or {}
    monto = data.get("monto")
    usuario = data.get("usuario")
    caja_id = data.get("caja_id")

    if not monto or float(monto) <= 0:
        return jsonify({"success": False, "message": "Monto inválido"}), 400

    fecha_hoy = str(date.today())

    try:
        from services.supabase_client import supabase

        caja_target = None
        if caja_id:
            caja_res = (
                supabase.table("caja")
                .select("id_caja, subtotal, fecha, turno")
                .eq("id_caja", caja_id)
                .execute()
            )
            caja_target = (caja_res.data or [{}])[0]

        if not caja_target:
            caja_res = (
                supabase.table("caja")
                .select("id_caja, subtotal, fecha, turno")
                .eq("fecha", fecha_hoy)
                .neq("turno", "cerrada")
                .order("id_caja", desc=True)
                .limit(1)
                .execute()
            )
            cajas = caja_res.data or []
            caja_target = cajas[0] if cajas else None

        caja_target_id = caja_target.get("id_caja") if caja_target else None

        # 1. Registrar retiro como gasto con tipo "Retiro" vinculando la caja activa
        gasto = create_gasto(
            monto=float(monto),
            fecha=fecha_hoy,
            caja_id=caja_target_id,
            tipo="Retiro"
        )

        if not gasto:
            return jsonify({"success": False, "message": "Error al registrar retiro"}), 500

        # 2. Actualizar tabla caja: restar el monto del subtotal de la caja vinculada
        if caja_target_id:
            nuevo_subtotal = float(caja_target.get("subtotal") or 0) - float(monto)
            supabase.table("caja").update({
                "subtotal": round(nuevo_subtotal, 2)
            }).eq("id_caja", caja_target_id).execute()
        else:
            supabase.table("caja").insert({
                "fecha": fecha_hoy,
                "turno": "diurno",
                "subtotal": round(-float(monto), 2)
            }).execute()

    except Exception as exc:
        print(f"[registrar_retiro] Error actualizando tabla caja: {exc}")
        return jsonify({"success": False, "message": "Error al registrar retiro"}), 500

    # 3. Actualizar saldo acumulado en tabla pago (resta por retiro)
    try:
        restar_monto_empresa(float(monto))
    except Exception as exc:
        print(f"[registrar_retiro] Error actualizando tabla pago (saldo empresa): {exc}")

    return jsonify({
        "success": True,
        "message": f"Retiro de S/ {monto} registrado correctamente",
        "data": {
            "gasto": gasto,
            "caja_id": caja_target_id,
            "usuario": usuario,
        }
    })
