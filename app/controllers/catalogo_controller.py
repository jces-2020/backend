# -*- coding: utf-8 -*-
"""
Controlador de catálogo: categorías y stock.
"""
from flask import Blueprint, jsonify
from app.services.supabase_client import supabase
import logging

logger = logging.getLogger(__name__)

catalogo_bp = Blueprint('catalogo', __name__, url_prefix='/api')


@catalogo_bp.route('/categorias', methods=['GET'])
def listar_categorias():
    try:
        resp = supabase.table('categoria').select('*').execute()
        if getattr(resp, 'error', None):
            return jsonify({'error': str(resp.error)}), 500
        return jsonify(resp.data or [])
    except Exception as e:
        logger.error(f"Error en listar_categorias: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@catalogo_bp.route('/stock', methods=['GET'])
def listar_stock():
    try:
        resp = supabase.table('stock').select('*').execute()
        if getattr(resp, 'error', None):
            return jsonify({'error': str(resp.error)}), 500
        return jsonify(resp.data or [])
    except Exception as e:
        return jsonify({'error': str(e)}), 500
