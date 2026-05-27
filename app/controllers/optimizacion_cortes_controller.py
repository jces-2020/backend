# -*- coding: utf-8 -*-
"""
Controller: Optimización de Cortes
Maneja el workflow de optimización de materiales (VIDRIO/ALUMINIO).
Gateway hacia el backend de optimización (puerto 5003).
"""
from flask import Blueprint, jsonify, request
from typing import List, Dict, Any
from services.optimizacion_cortes_service import (
    calcular_cortes_optimizados,
    get_retasos_inventario,
    guardar_optimizacion_cortes,
    get_optimizacion_by_id,
    generar_pdf_cortes
)

optimizacion_cortes_bp = Blueprint("optimizacion_cortes_bp", __name__, url_prefix="/api/optimizacion-cortes")


@optimizacion_cortes_bp.route("/calcular", methods=["POST"])
def calcular_optimizacion():
    """
    Calcula la optimización de cortes basada en productos seleccionados.
    Body: {
        "productos": [{ "id": str, "cantidad": int, "ancho"?: float, "alto"?: float, "largo"?: float }],
        "tipo_material": "vidrio" | "aluminio",
        "plancha_ancho"?: float (default 300),
        "plancha_alto"?: float (default 300),
        "barra_largo"?: float (default 300),
        "permitir_rotacion"?: bool (default true),
        "min_retazo"?: float (default 20)
    }
    """
    try:
        data = request.get_json()
        productos = data.get("productos", [])
        tipo_material = data.get("tipo_material", "vidrio")

        if not productos:
            return jsonify({"success": False, "message": "Productos requeridos"}), 400

        # Parámetros opcionales
        plancha_ancho = float(data.get("plancha_ancho", 300.0))
        plancha_alto = float(data.get("plancha_alto", 300.0))
        barra_largo = float(data.get("barra_largo", 300.0))
        permitir_rotacion = data.get("permitir_rotacion", True)
        min_retazo = float(data.get("min_retazo", 20.0))

        resultado = calcular_cortes_optimizados(
            productos=productos,
            tipo_material=tipo_material,
            plancha_ancho=plancha_ancho,
            plancha_alto=plancha_alto,
            barra_largo=barra_largo,
            permitir_rotacion=permitir_rotacion,
            min_retazo=min_retazo
        )

        if resultado.get("success"):
            return jsonify(resultado), 200
        else:
            return jsonify(resultado), 500

    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@optimizacion_cortes_bp.route("/retasos", methods=["GET"])
def get_retasos_disponibles():
    """
    Obtiene la lista de retazos disponibles en inventario.
    """
    try:
        retasos = get_retasos_inventario()

        return jsonify({
            "success": True,
            "data": retasos
        }), 200

    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@optimizacion_cortes_bp.route("/guardar", methods=["POST"])
def guardar_optimizacion():
    """
    Guarda los resultados de la optimización.
    Body: {
        "cliente": str,
        "fecha": str,
        "productos_seleccionados": [],
        "resultado_optimizacion": {} // resultado del endpoint /calcular
    }
    """
    try:
        data = request.get_json()

        cliente = data.get("cliente")
        if not cliente:
            return jsonify({"success": False, "message": "Cliente requerido"}), 400

        resultado = guardar_optimizacion_cortes(data)

        if resultado:
            return jsonify({
                "success": True,
                "data": resultado,
                "message": "Optimización guardada correctamente"
            }), 200
        else:
            return jsonify({"success": False, "message": "Error al guardar"}), 500

    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@optimizacion_cortes_bp.route("/pdf", methods=["POST"])
def descargar_pdf_optimizacion():
    """
    Genera un PDF con el reporte visual de cortes de vidrio.
    Body: igual que /calcular para vidrio + { cliente?, referencia? }
    """
    from flask import make_response
    try:
        data = request.get_json()
        productos = data.get("productos", [])
        if not productos:
            return jsonify({"success": False, "message": "Productos requeridos"}), 400

        pdf_bytes = generar_pdf_cortes(
            productos=productos,
            plancha_ancho=float(data.get("plancha_ancho", 300.0)),
            plancha_alto=float(data.get("plancha_alto", 300.0)),
            permitir_rotacion=data.get("permitir_rotacion", True),
            cliente=data.get("cliente"),
            referencia=data.get("referencia"),
        )

        if pdf_bytes is None:
            return jsonify({"success": False, "message": "Error generando PDF"}), 500

        response = make_response(pdf_bytes)
        response.headers["Content-Type"] = "application/pdf"
        response.headers["Content-Disposition"] = "attachment; filename=reporte_cortes.pdf"
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Expose-Headers"] = "Content-Disposition"
        return response

    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@optimizacion_cortes_bp.route("/<optimizacion_id>", methods=["GET"])
def get_optimizacion_detalle(optimizacion_id: str):
    """
    Obtiene el detalle de una optimización específica.
    """
    try:
        optimizacion = get_optimizacion_by_id(optimizacion_id)

        if optimizacion:
            return jsonify({
                "success": True,
                "data": optimizacion
            }), 200
        else:
            return jsonify({
                "success": False,
                "message": "Optimización no encontrada"
            }), 404

    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
