from flask import Blueprint, jsonify
from services.supabase_client import supabase
import random

servicios_random_bp = Blueprint('servicios_random', __name__)

@servicios_random_bp.route('/api/servicios/random', methods=['GET'])
def get_servicios_random():
    try:
        # Obtener todos los servicios
        result = supabase.table('servicio').select('id_servicio, nombre, descripcion, ING').execute()
        servicios = result.data or []
        
        # Generar URLs públicas para las imágenes
        data_with_urls = []
        for item in servicios:
            public_url = None
            if 'ING' in item and item['ING']:
                image_path_or_url = item['ING']
                if image_path_or_url.startswith('http'):
                    public_url = image_path_or_url
                else:
                    try:
                        public_url = supabase.storage.from_('IMG').get_public_url(image_path_or_url)
                    except Exception as e:
                        print(f"Error al generar la URL pública para '{image_path_or_url}': {e}")
            item['imagen_public_url'] = public_url
            data_with_urls.append(item)
        
        # Mezclar aleatoriamente y tomar 5
        random.shuffle(data_with_urls)
        servicios_random = data_with_urls[:5]
        return jsonify({"success": True, "data": servicios_random}), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 400
