"""
Controller de Ubicacion / Geocodificacion
Endpoints:

POST /api/reverse-geocode
"""

import os
import requests
from flask import Blueprint, request, jsonify

ubicacion_bp = Blueprint('ubicacion', __name__, url_prefix='/api')

GOOGLE_GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"


@ubicacion_bp.route('/reverse-geocode', methods=['POST'])
def reverse_geocode():
    try:
        datos = request.get_json() or {}
        lat = datos.get("lat")
        lng = datos.get("lng")

        if lat is None or lng is None:
            return jsonify({"success": False, "message": "lat y lng son requeridos"}), 400

        api_key = os.getenv("GOOGLE_MAPS_API_KEY", "").strip()
        if not api_key:
            return jsonify({"success": False, "message": "GOOGLE_MAPS_API_KEY no configurada"}), 500

        response = requests.get(GOOGLE_GEOCODE_URL, params={
            "latlng": f"{lat},{lng}",
            "key": api_key,
            "language": "es",
        }, timeout=8)
        data = response.json()

        if data.get("status") != "OK" or not data.get("results"):
            return jsonify({
                "success": False,
                "message": data.get("status", "Sin resultados")
            }), 200

        primero = data["results"][0]

        return jsonify({
            "success": True,
            "direccion": primero.get("formatted_address", ""),
            "place_id": primero.get("place_id"),
        }), 200

    except requests.RequestException as e:
        return jsonify({"success": False, "message": str(e)}), 502
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
