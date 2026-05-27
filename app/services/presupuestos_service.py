from typing import List, Dict, Optional
from services.supabase_client import supabase
from datetime import datetime


def obtiene_cliente_por_documento(documento: str) -> Optional[str]:
    """Busca un cliente por su documento y devuelve el id_cliente si existe."""
    try:
        resp = supabase.table('cliente').select('id_cliente').eq('documento', documento).limit(1).execute()
        if resp.data and len(resp.data) > 0:
            return resp.data[0].get('id_cliente')
    except Exception as e:
        print(f"Error al buscar cliente por documento: {str(e)}")
    return None



def guardar_presupuesto(data: Dict) -> Dict:
    """
    Guarda un nuevo presupuesto calculando automáticamente los costos
    """
    try:
        # Ajustar datos al nuevo esquema de la tabla `presupuesto`
        cliente_id = data.get('cliente_id')
        servicio_id = data.get('servicio_id')
        if not servicio_id:
            raise ValueError('servicio_id es obligatorio')
        # cliente_id puede ser None; se insertará como null si el esquema lo permite

        descripcion = data.get('descripcion') or data.get('servicio') or ''
        cantidad = int(data.get('cantidad', 1))
        precio_unitario = float(data.get('precio_unitario', 0))
        subtotal_val = float(data.get('subtotal', precio_unitario * cantidad))
        igv_val = float(data.get('igv', round(subtotal_val * 0.18, 2)))
        total_val = float(data.get('total', round(subtotal_val + igv_val, 2)))

        presupuesto = {
            'servicio_id': servicio_id,
            'descripcion': descripcion,
            'cantidad': cantidad,
            'precio_unitario': precio_unitario,
            'subtotal': subtotal_val,
            'igv': igv_val,
            'total': total_val
        }
        if cliente_id:
            presupuesto['cliente_id'] = cliente_id

        # insertar en la tabla singular
        result = supabase.table('presupuesto') \
            .insert(presupuesto) \
            .execute()

        if result.data:
            return {
                "success": True,
                "data": result.data[0]
            }

        return {
            "success": False,
            "message": "Error al guardar presupuesto"
        }

    except Exception as e:
        print(f"Error en guardar_presupuesto: {str(e)}")
        return {
            "success": False,
            "message": str(e)
        }


# ======================================================
# LISTAR PRESUPUESTOS
# ======================================================
def obtener_presupuestos(filtro: Optional[str] = None, servicio_id: Optional[str] = None) -> List[Dict]:
    try:
        # fetch from the singular table
        query = supabase.table('presupuesto') \
            .select('*') \
            .order('fecha_creacion', desc=True)

        if servicio_id:
            query = query.eq('servicio_id', servicio_id)

        if filtro:
            query = query.or_(
                f'cliente_documento.ilike.%{filtro}%,'
                f'cliente_razon_social.ilike.%{filtro}%'
            )

        result = query.execute()

        return result.data or []

    except Exception as e:
        print(f"Error en obtener_presupuestos: {str(e)}")
        return []


# ======================================================
# OBTENER POR ID
# ======================================================
def obtener_presupuesto_por_id(
    presupuesto_id: str
) -> Optional[Dict]:

    try:
        result = supabase.table('presupuesto') \
            .select('*') \
            .eq('id_presupuesto', presupuesto_id) \
            .single() \
            .execute()

        return result.data

    except Exception as e:
        print(f"Error en obtener_presupuesto_por_id: {str(e)}")
        return None