import sys
from flask import Blueprint, jsonify, request

from controllers.clientes_controller import verify_jwt
from services.cliente_grafico_service import ClienteGraficoService
from services.supabase_client import supabase


cliente_grafico_api = Blueprint(
    "cliente_grafico_api",
    __name__,
    url_prefix="/api/clientes"
)
bp = cliente_grafico_api  # alias para auto-registro del factory


@cliente_grafico_api.route("/grafico-pagos", methods=["GET"])
def obtener_grafico_pagos_cliente():
    try:
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"success": False, "message": "Token no proporcionado"}), 401

        token = auth_header.split(" ", 1)[1]
        payload = verify_jwt(token)
        if not payload:
            return jsonify({"success": False, "message": "Token invalido o expirado"}), 401

        cliente_id = payload.get("sub")
        if not cliente_id:
            return jsonify({"success": False, "message": "Cliente no identificado"}), 401

        mes = request.args.get("mes")
        print(f"[GRAFICO] cliente_id={cliente_id} mes={mes}", file=sys.stderr, flush=True)
        # Verificar cuántos registros existen para este cliente
        try:
            _dbg = supabase.table("venta").select("id_venta, fecha_venta, monto").eq("cliente_id", cliente_id).limit(5).execute()
            print(f"[GRAFICO] ventas en BD: {_dbg.data}", file=sys.stderr, flush=True)
        except Exception as _e:
            print(f"[GRAFICO] error debug: {_e}", file=sys.stderr, flush=True)
        resultado = ClienteGraficoService.obtener_grafico_pagos_mensuales(
            cliente_id=cliente_id,
            mes=mes
        )

        if not resultado.get("success"):
            return jsonify({
                "success": False,
                "message": resultado.get("message") or "No se pudo generar el grafico"
            }), 400

        return jsonify({
            "success": True,
            "data": resultado.get("data") or {}
        }), 200
    except Exception as exc:
        return jsonify({"success": False, "message": str(exc)}), 500