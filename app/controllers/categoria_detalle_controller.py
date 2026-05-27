# -*- coding: utf-8 -*-
from flask import Blueprint, jsonify, request
from app.services.supabase_client import supabase

categoria_detalle_bp = Blueprint('categoria_detalle_bp', __name__)


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
        return jsonify({'success': False, 'error': str(e)}), 500


@categoria_detalle_bp.route('/api/categorias/detalles', methods=['GET'])
def get_todos_detalles():
    """Devuelve todos los detalles con el nombre de su categoría."""
    try:
        resp = supabase.table('categoria_detalle') \
            .select('*, categoria:categoria_id (id_categoria, descripcion)') \
            .execute()
        data = resp.data or []
        # Aplanar: agregar categoria_nombre al nivel raíz
        for row in data:
            cat = row.pop('categoria', None) or {}
            row['categoria_nombre'] = (cat.get('descripcion') or '').upper()
        return jsonify({'success': True, 'data': data}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
