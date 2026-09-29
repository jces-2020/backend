from app.services.supabase_client import supabase

def get_all_servicios():
    """
    Obtiene todos los servicios de la base de datos y genera las URLs públicas para las imágenes.
    """
    try:
        response = supabase.table('servicio').select('*').execute()
        
        if not response.data:
            return []

        data_with_urls = []
        for item in response.data:
            public_url = None
            # La columna 'ING' contiene la ruta o la URL de la imagen
            if 'ING' in item and item['ING']:
                image_path_or_url = item['ING']
                
                # Si ya es una URL completa, la usamos directamente
                if image_path_or_url.startswith('http'):
                    public_url = image_path_or_url
                else:
                    # Si es una ruta, generamos la URL pública desde el bucket 'IMG'
                    try:
                        public_url = supabase.storage.from_('IMG').get_public_url(image_path_or_url)
                    except Exception as e:
                        print(f"Error al generar la URL pública para '{image_path_or_url}': {e}")
            
            item['imagen_public_url'] = public_url
            data_with_urls.append(item)

        return data_with_urls

    except Exception as e:
        print(f"Error al obtener los servicios: {e}")
        return None
