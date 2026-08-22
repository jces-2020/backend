"""
Controller de Ubicacion / Geocodificacion
Endpoints:

POST /api/reverse-geocode
GET  /api/ubicacion/ruta/<carrito_id>
"""

import os
import requests
from flask import Blueprint, request, jsonify

from app.controllers.pedidos_detalle_controller import _require_personal
from app.services.supabase_client import supabase
from app.services.venta_detalle_service import obtener_cliente_id_por_carrito

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


@ubicacion_bp.route('/ubicacion/ruta/<carrito_id>', methods=['GET'])
def obtener_ubicacion_para_ruta(carrito_id):
    """Resuelve la ultima ubicacion guardada del cliente dueno de un carrito.

    Usado por Entrega/Servicio (OBRAS) para trazar la ruta de entrega en el mapa.
    """
    try:
        ok, resp = _require_personal(request, allowed_areas=['ALMACEN', 'ADMINISTRACION', 'OBRAS', 'TRABAJO'])
        if not ok:
            return resp

        cliente_id = obtener_cliente_id_por_carrito(carrito_id)
        if not cliente_id:
            return jsonify({"success": False, "message": "No se pudo resolver el cliente de este carrito"}), 404

        ubi_res = (
            supabase.table("ubicacion")
            .select("direccion, referencia, latitud, longitud, fecha_creacion")
            .eq("cliente_id", cliente_id)
            .order("fecha_creacion", desc=True)
            .limit(1)
            .execute()
        )
        filas = getattr(ubi_res, "data", []) or []
        if not filas or filas[0].get("latitud") is None or filas[0].get("longitud") is None:
            return jsonify({"success": False, "message": "El cliente no tiene una ubicacion guardada"}), 200

        ubicacion = filas[0]
        return jsonify({
            "success": True,
            "cliente_id": cliente_id,
            "direccion": ubicacion.get("direccion"),
            "referencia": ubicacion.get("referencia"),
            "latitud": float(ubicacion.get("latitud")),
            "longitud": float(ubicacion.get("longitud")),
        }), 200

    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

