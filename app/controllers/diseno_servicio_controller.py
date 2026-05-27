# -*- coding: utf-8 -*-
"""
Controller: Diseño de Servicios
Diseño y cálculo de materiales para ventanas, puertas, mamparas y demás servicios.
Endpoint principal: POST /api/diseno-servicio/calcular
"""
from flask import Blueprint, jsonify, request
from services.diseno_servicio_service import calcular_diseno_servicio

diseno_servicio_bp = Blueprint(
    "diseno_servicio_bp", __name__, url_prefix="/api/diseno-servicio"
)


@diseno_servicio_bp.route("/calcular", methods=["POST"])
def calcular():
    """
    Diseña un servicio (ventana, puerta, mampara, etc.) y calcula los materiales.

    Body JSON:
        nombre_servicio  str    Nombre del servicio, ej. "Puerta de Aluminio"
        ancho            float  Ancho en cm
        alto             float  Alto en cm
        tipo             str    (opcional) puerta|ventana|mampara|generico — se auto-detecta si no se envía
        barra_largo      float  (opcional) Largo de barra de aluminio, default 300 cm
        plancha_ancho    float  (opcional) Ancho de plancha de vidrio, default 300 cm
        plancha_alto     float  (opcional) Alto de plancha de vidrio, default 300 cm

    Response:
        success          bool
        tipo             str    Tipo detectado
        aluminio         obj    Cortes, distribución en barras, totales lineales
        vidrio           obj    Paneles, planchas necesarias, % de uso
        diseno           obj    Posiciones en cm para el blueprint SVG del frontend
    """
    try:
        data = request.get_json() or {}

        nombre_servicio = str(data.get("nombre_servicio", "")).strip()
        ancho = float(data.get("ancho", 0))
        alto  = float(data.get("alto",  0))

        if ancho <= 0 or alto <= 0:
            return jsonify({
                "success": False,
                "message": "Los campos ancho y alto deben ser mayores a 0"
            }), 400

        resultado = calcular_diseno_servicio(
            nombre_servicio=nombre_servicio,
            ancho=ancho,
            alto=alto,
            tipo=data.get("tipo") or None,
            barra_largo=float(data.get("barra_largo", 300.0)),
            plancha_ancho=float(data.get("plancha_ancho", 300.0)),
            plancha_alto=float(data.get("plancha_alto", 300.0)),
        )

        if resultado.get("success"):
            return jsonify(resultado), 200
        return jsonify(resultado), 500

    except ValueError:
        return jsonify({"success": False, "message": "ancho y alto deben ser números válidos"}), 400
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@diseno_servicio_bp.route("/tipos", methods=["GET"])
def listar_tipos():
    """Devuelve los tipos de servicio soportados por el motor de diseño."""
    return jsonify({
        "success": True,
        "tipos": [
            {"key": "puerta",   "label": "Puerta de Aluminio"},
            {"key": "ventana",  "label": "Ventana"},
            {"key": "mampara",  "label": "Mampara"},
            {"key": "generico", "label": "Genérico"},
        ]
    }), 200
