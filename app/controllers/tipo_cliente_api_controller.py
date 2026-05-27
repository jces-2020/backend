from flask import Blueprint, jsonify
from app.services.supabase_client import supabase

bp = Blueprint('tipo_cliente_api', __name__)

@bp.route('/api/tipo_cliente', methods=['GET'])
def get_tipos_cliente():
    try:
        res = supabase.table('tipo_cliente').select('*').execute()
        tipos = res.data if hasattr(res, 'data') else []
        return jsonify({'success': True, 'tipos': tipos}), 200
    except Exception as e:
        return jsonify({'success': False, 'message': 'Error al consultar tipo_cliente', 'error': str(e)}), 500
