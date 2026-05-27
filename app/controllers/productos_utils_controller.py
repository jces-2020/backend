from flask import Blueprint, jsonify
from app.services.supabase_client import supabase

productos_utils_bp = Blueprint('productos_utils', __name__)

@productos_utils_bp.route('/productos/ids')
def listar_ids_productos():
    response = supabase.table('productos').select('id_producto, nombre, grosor, codigo, descripcion, precio_unitario').execute()
    return jsonify(response.data)