from flask import Blueprint, jsonify, request
from datetime import date

from services.cuadre_service import get_resumen_mes, get_pagos_listado

cuadre_caja_diario_bp = Blueprint("cuadre_caja_diario_bp", __name__)


@cuadre_caja_diario_bp.route("/api/cuadre-caja/pagos", methods=["GET"])
def cuadre_pagos():
    mes = request.args.get("mes")
    if not mes:
        # por defecto el mes actual
        today = date.today()
        mes = f"{today.year}-{str(today.month).zfill(2)}"
    data = get_pagos_listado(mes)
    return jsonify({"success": True, "data": data, "mes": mes})


@cuadre_caja_diario_bp.route("/api/cuadre-caja/resumen", methods=["GET"])
def cuadre_resumen():
    mes = request.args.get("mes")
    if not mes:
        today = date.today()
        mes = f"{today.year}-{str(today.month).zfill(2)}"
    data = get_resumen_mes(mes)
    return jsonify({"success": True, "data": data})
