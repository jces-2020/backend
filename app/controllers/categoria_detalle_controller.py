# -*- coding: utf-8 -*-
import traceback
from flask import Blueprint, jsonify, request
from app.services.supabase_client import supabase

categoria_detalle_bp = Blueprint('categoria_detalle_bp', __name__)


def _log_error(tag, categoria_id, e):
    print(f"[CATEGORIA_DETALLE][{tag}] categoria_id={categoria_id} error={type(e).__name__}: {e}", flush=True)
    print(traceback.format_exc(), flush=True)


@categoria_detalle_bp.route('/api/categorias/<categoria_id>/detalle', methods=['GET'])
def get_detalle(categoria_id):
    try:
        resp = supabase.table('categoria_detalle') \
            .select('*') \
            .eq('categoria_id', categoria_id) \
            .limit(1) \
            .execute()
        data = resp.data or []
        if not data:
            return jsonify({'success': True, 'data': None}), 200
        return jsonify({'success': True, 'data': data[0]}), 200
    except Exception as e:
        _log_error('GET', categoria_id, e)
        return jsonify({'success': False, 'error': str(e)}), 500


@categoria_detalle_bp.route('/api/categorias/<categoria_id>/detalle', methods=['POST'])
def upsert_detalle(categoria_id):
    try:
        body = request.get_json() or {}
        campos_permitidos = [
            'forma', 'serie', 'uso_servicio',
            'rebaje_mm', 'cara_visible_mm', 'canal_ancho_mm',
            'barra_largo_cm', 'tolerancia_mm',
            'espesor_mm', 'plancha_ancho_cm', 'plancha_alto_cm',
            'medidas',
        ]
        payload = {k: body[k] for k in campos_permitidos if k in body}
        if not payload:
            return jsonify({'success': False, 'error': 'Sin campos para guardar'}), 400

        # Verificar si ya existe
        existe = supabase.table('categoria_detalle') \
            .select('id') \
            .eq('categoria_id', categoria_id) \
            .limit(1) \
            .execute()

        if existe.data:
            resp = supabase.table('categoria_detalle') \
                .update(payload) \
                .eq('categoria_id', categoria_id) \
                .execute()
        else:
            payload['categoria_id'] = categoria_id
            resp = supabase.table('categoria_detalle') \
                .insert(payload) \
                .execute()

        data = resp.data[0] if resp.data else payload
        return jsonify({'success': True, 'data': data}), 200
    except Exception as e:
        _log_error('POST', categoria_id, e)
        return jsonify({'success': False, 'error': str(e)}), 500


@categoria_detalle_bp.route('/api/categorias/detalles', methods=['GET'])
def get_todos_detalles():
    """
    Devuelve, por categoría, las medidas máximas de plancha/barra disponibles.

    'categoria_detalle' (un registro por categoría) ya no existe: las medidas
    ahora se guardan por producto en 'detalle_producto'. Acá se agregan
    (tomando el máximo) para mantener el mismo formato de respuesta que
    esperan los consumidores existentes (medida "techo" por categoría).
    """
    try:
        resp = supabase.table('detalle_producto') \
            .select('plancha_ancho_cm, plancha_alto_cm, barra_largo_cm, '
                     'productos!inner(categoria_id, categoria(id_categoria, descripcion))') \
            .execute()
        rows = resp.data or []

        agregados = {}
        for row in rows:
            producto = row.get('productos') or {}
            categoria_id = producto.get('categoria_id')
            if not categoria_id:
                continue
            categoria = producto.get('categoria') or {}
            acc = agregados.setdefault(categoria_id, {
                'categoria_id': categoria_id,
                'categoria_nombre': (categoria.get('descripcion') or '').upper(),
                'plancha_ancho_cm': 0,
                'plancha_alto_cm': 0,
                'barra_largo_cm': 0,
            })
            acc['plancha_ancho_cm'] = max(acc['plancha_ancho_cm'], float(row.get('plancha_ancho_cm') or 0))
            acc['plancha_alto_cm'] = max(acc['plancha_alto_cm'], float(row.get('plancha_alto_cm') or 0))
            acc['barra_largo_cm'] = max(acc['barra_largo_cm'], float(row.get('barra_largo_cm') or 0))

        return jsonify({'success': True, 'data': list(agregados.values())}), 200
    except Exception as e:
        _log_error('GET /detalles', None, e)
        return jsonify({'success': False, 'error': str(e)}), 500
