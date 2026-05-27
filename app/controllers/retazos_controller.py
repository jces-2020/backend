from flask import Blueprint, jsonify, request
from app.services.supabase_client import supabase

retazos_bp = Blueprint("retazos", __name__)


def _to_float(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return default


def _to_int(value, default=0):
    try:
        return int(value)
    except Exception:
        return default


@retazos_bp.route("/api/retazos/categorias", methods=["GET"])
def listar_categorias_retazo():
    try:
        res = supabase.table("categoria").select("id_categoria, descripcion").order("descripcion").execute()
        return jsonify({"success": True, "data": res.data or []}), 200
    except Exception as exc:
        return jsonify({"success": False, "message": f"No se pudieron cargar categorías: {str(exc)}", "data": []}), 500


@retazos_bp.route("/api/retazos", methods=["POST"])
def guardar_retazo():
    data = request.get_json() or {}

    id_categoria = (data.get("id_categoria") or "").strip()
    nombre = (data.get("nombre") or "").strip()
    lugar = (data.get("lugar") or "").strip()
    descripcion = (data.get("descripcion") or "").strip()

    ancho_cm = _to_float(data.get("ancho_cm"), 0.0)
    alto_cm = _to_float(data.get("alto_cm"), 0.0)
    cantidad = _to_int(data.get("cantidad"), 0)
    area = _to_float(data.get("area"), 0.0)

    if not id_categoria:
        return jsonify({"success": False, "message": "La categoría es obligatoria"}), 400
    if not nombre:
        return jsonify({"success": False, "message": "El nombre es obligatorio"}), 400
    if not lugar:
        return jsonify({"success": False, "message": "El lugar es obligatorio"}), 400
    if ancho_cm <= 0 or alto_cm <= 0:
        return jsonify({"success": False, "message": "Ancho y alto deben ser mayores a 0"}), 400
    if cantidad <= 0:
        return jsonify({"success": False, "message": "La cantidad debe ser mayor a 0"}), 400

    if area <= 0:
        area = round(ancho_cm * alto_cm, 3)

    payload = {
        "id_categoria": id_categoria,
        "ancho_cm": ancho_cm,
        "alto_cm": alto_cm,
        "lugar": lugar[:50],
        "nombre": nombre[:20],
        "cantidad": cantidad,
        "descripción": descripcion[:20],
        "area": area,
    }

    try:
        ins = supabase.table("merma").insert(payload).execute()
        nuevo = (ins.data or [None])[0]
        return jsonify({"success": True, "data": nuevo}), 201
    except Exception as exc:
        return jsonify({"success": False, "message": f"No se pudo guardar el retazo: {str(exc)}"}), 500
