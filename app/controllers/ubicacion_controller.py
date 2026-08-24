"""
Controller de Ubicacion / Geocodificacion
Endpoints:

POST /api/reverse-geocode
GET  /api/ubicacion/ruta/<carrito_id>
GET  /api/ubicacion/ruta/presupuesto/<presupuesto_id>
"""

import os
import requests
from flask import Blueprint, request, jsonify

from app.controllers.pedidos_detalle_controller import _require_personal
from app.services.supabase_client import supabase
from app.services.venta_detalle_service import obtener_cliente_id_por_carrito

ubicacion_bp = Blueprint('ubicacion', __name__, url_prefix='/api')

GOOGLE_GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"
GOOGLE_DIRECTIONS_URL = "https://maps.googleapis.com/maps/api/directions/json"


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


@ubicacion_bp.route('/directions', methods=['GET'])
def obtener_direcciones():
    """Ruta (polyline) entre dos puntos vía Directions API de Google.

    Se llama desde el backend (no directo desde el navegador/app) porque la
    API REST de Directions no admite CORS para requests desde el cliente.
    Query params: origen_lat, origen_lng, destino_lat, destino_lng.
    """
    try:
        origen_lat = request.args.get('origen_lat')
        origen_lng = request.args.get('origen_lng')
        destino_lat = request.args.get('destino_lat')
        destino_lng = request.args.get('destino_lng')

        if not all([origen_lat, origen_lng, destino_lat, destino_lng]):
            return jsonify({"success": False, "message": "origen y destino son requeridos"}), 400

        api_key = os.getenv("GOOGLE_MAPS_API_KEY", "").strip()
        if not api_key:
            return jsonify({"success": False, "message": "GOOGLE_MAPS_API_KEY no configurada"}), 500

        response = requests.get(GOOGLE_DIRECTIONS_URL, params={
            "origin": f"{origen_lat},{origen_lng}",
            "destination": f"{destino_lat},{destino_lng}",
            "key": api_key,
        }, timeout=10)
        data = response.json()

        if data.get("status") != "OK" or not data.get("routes"):
            return jsonify({"success": False, "message": data.get("status", "Sin ruta")}), 200

        ruta = data["routes"][0]
        leg = (ruta.get("legs") or [{}])[0]

        return jsonify({
            "success": True,
            "polyline": ruta.get("overview_polyline", {}).get("points", ""),
            "distancia_texto": leg.get("distance", {}).get("text"),
            "duracion_texto": leg.get("duration", {}).get("text"),
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

        # 1) Ubicacion guardada especificamente para ESTE pedido (carrito_id
        # exacto) -- un mismo cliente puede tener varias direcciones si hizo
        # varios pedidos, y cada una vive en una fila distinta de ubicacion.
        filas = []
        try:
            ubi_carrito = (
                supabase.table("ubicacion")
                .select("direccion, referencia, latitud, longitud, fecha_creacion")
                .eq("carrito_id", carrito_id)
                .order("fecha_creacion", desc=True)
                .limit(1)
                .execute()
            )
            filas = getattr(ubi_carrito, "data", []) or []
        except Exception as exc_carrito:
            print(f"[ubicacion_ruta] WARN no se pudo filtrar por carrito_id: {exc_carrito}")

        # 2) Respaldo: pedidos anteriores a este enlace (o si por algun motivo
        # no quedo guardado el carrito_id) -- se usa la mas reciente del cliente.
        if not filas:
            ubi_cliente = (
                supabase.table("ubicacion")
                .select("direccion, referencia, latitud, longitud, fecha_creacion")
                .eq("cliente_id", cliente_id)
                .order("fecha_creacion", desc=True)
                .limit(1)
                .execute()
            )
            filas = getattr(ubi_cliente, "data", []) or []

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


@ubicacion_bp.route('/ubicacion/ruta/presupuesto/<presupuesto_id>', methods=['GET'])
def obtener_ubicacion_para_ruta_presupuesto(presupuesto_id):
    """Ubicacion guardada para un presupuesto de servicio (visita de remetro).

    A diferencia de un pedido de producto, un servicio recien cotizado
    todavia no tiene carrito_compras -- la ubicacion se guardo directo con
    presupuesto_id al crear la cotizacion (ver presupuesto_cliente_service.py).
    """
    try:
        ok, resp = _require_personal(request, allowed_areas=['ALMACEN', 'ADMINISTRACION', 'OBRAS', 'TRABAJO'])
        if not ok:
            return resp

        ubi_res = (
            supabase.table("ubicacion")
            .select("cliente_id, direccion, referencia, latitud, longitud, fecha_creacion")
            .eq("presupuesto_id", presupuesto_id)
            .order("fecha_creacion", desc=True)
            .limit(1)
            .execute()
        )
        filas = getattr(ubi_res, "data", []) or []
        if not filas or filas[0].get("latitud") is None or filas[0].get("longitud") is None:
            return jsonify({"success": False, "message": "No hay ubicacion guardada para este servicio"}), 200

        ubicacion = filas[0]
        return jsonify({
            "success": True,
            "cliente_id": ubicacion.get("cliente_id"),
            "direccion": ubicacion.get("direccion"),
            "referencia": ubicacion.get("referencia"),
            "latitud": float(ubicacion.get("latitud")),
            "longitud": float(ubicacion.get("longitud")),
        }), 200

    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
