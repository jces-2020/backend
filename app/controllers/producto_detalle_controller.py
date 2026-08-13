# -*- coding: utf-8 -*-
import traceback
from flask import Blueprint, jsonify, request
from app.services.supabase_client import supabase

producto_detalle_bp = Blueprint('producto_detalle_bp', __name__)

DETALLE_FIELDS = [
    'forma', 'serie', 'uso_servicio',
    'rebaje_mm', 'cara_visible_mm', 'canal_ancho_mm',
    'barra_largo_cm', 'tolerancia_mm',
    'espesor_mm', 'plancha_ancho_cm', 'plancha_alto_cm',
    'medidas'
]


def _extract_detalle_payload(body):
    return {k: body[k] for k in DETALLE_FIELDS if k in body}


def _upsert_detalle_producto(producto_id, payload):
    if not payload:
        return None

    existe = supabase.table('detalle_producto') \
        .select('id') \
        .eq('producto_id', producto_id) \
        .limit(1) \
        .execute()

    if getattr(existe, 'data', None):
        resp = supabase.table('detalle_producto') \
            .update(payload) \
            .eq('producto_id', producto_id) \
            .execute()
    else:
        resp = supabase.table('detalle_producto') \
            .insert({**payload, 'producto_id': producto_id}) \
            .execute()

    return getattr(resp, 'data', None) or None


@producto_detalle_bp.route('/api/productos/<producto_id>/detalle', methods=['GET'])
def get_detalle(producto_id):
    try:
        resp = supabase.table('detalle_producto') \
            .select('*') \
            .eq('producto_id', producto_id) \
            .limit(1) \
            .execute()
        data = getattr(resp, 'data', None) or []
        if not data:
            return jsonify({'success': True, 'data': None}), 200
        return jsonify({'success': True, 'data': data[0]}), 200
    except Exception as e:
        print(f"[PRODUCTO_DETALLE][GET] producto_id={producto_id} error={type(e).__name__}: {e}", flush=True)
        print(traceback.format_exc(), flush=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@producto_detalle_bp.route('/api/productos/<producto_id>/detalle', methods=['POST'])
def upsert_detalle(producto_id):
    try:
        body = request.get_json() or {}
        payload = _extract_detalle_payload(body)
        if not payload:
            return jsonify({'success': False, 'error': 'Sin campos para guardar'}), 400

        data = _upsert_detalle_producto(producto_id, payload)
        if data is None:
            return jsonify({'success': False, 'error': 'No se pudo guardar el detalle'}), 500

        return jsonify({'success': True, 'data': data}), 200
    except Exception as e:
        print(
            f"[PRODUCTO_DETALLE][POST] producto_id={producto_id} campos={list(payload.keys()) if 'payload' in locals() else '?'} "
            f"error={type(e).__name__}: {e}",
            flush=True,
        )
        print(traceback.format_exc(), flush=True)
        return jsonify({'success': False, 'error': str(e)}), 500
