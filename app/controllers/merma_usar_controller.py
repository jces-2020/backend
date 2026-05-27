from flask import Blueprint, request, jsonify
from services.supabase_client import supabase

bp = Blueprint('merma_usar', __name__, url_prefix='/api/merma')

@bp.route('/usar', methods=['POST'])
def usar_mermas():
    """
    Descuenta mermas usadas en tiempo real.
    Elimina la merma si cantidad llega a 0.
    """
    data = request.get_json()
    mermas = data.get('mermas', [])
    
    if not mermas:
        return jsonify({"success": False, "message": "No hay mermas para descontar"}), 400
    
    try:
        eliminadas = 0
        actualizadas = 0
        
        for item in mermas:
            id_merma = item['id_merma']
            cantidad_usada = item['cantidad_usada']
            
            # Obtener merma actual
            result = supabase.table('merma').select('cantidad, nombre').eq('id_merma', id_merma).execute()
            if not result.data:
                continue
            
            cantidad_actual = result.data[0]['cantidad']
            nombre_merma = result.data[0]['nombre']
            nueva_cantidad = cantidad_actual - cantidad_usada
            
            # Si llega a 0 o menos, eliminar; si no, actualizar
            if nueva_cantidad <= 0:
                supabase.table('merma').delete().eq('id_merma', id_merma).execute()
                eliminadas += 1
            else:
                supabase.table('merma').update({"cantidad": nueva_cantidad}).eq('id_merma', id_merma).execute()
                actualizadas += 1
        
        mensaje = f"Operación completada: {actualizadas} merma(s) actualizada(s), {eliminadas} merma(s) eliminada(s)"
        return jsonify({"success": True, "message": mensaje, "actualizadas": actualizadas, "eliminadas": eliminadas}), 200
    
    except Exception as e:
        return jsonify({"success": False, "message": f"Error al descontar mermas: {str(e)}"}), 500
