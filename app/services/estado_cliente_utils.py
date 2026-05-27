from app.services.supabase_client import supabase

def get_estado_cliente_id_proceso():
    """Obtiene el id de estado_cliente para 'en proceso' o 'proceso'."""
    try:
        res = supabase.table('estado_cliente').select('id_estado, descripcion').execute()
        for row in getattr(res, 'data', []) or []:
            desc = (row.get('descripcion') or '').strip().lower()
            if desc in ('en proceso', 'proceso'):
                return row.get('id_estado')
    except Exception as e:
        print(f"Error buscando estado_cliente_id para 'en proceso': {e}")
    return None
