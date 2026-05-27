"""
Servicio para gestión de clientes en el panel de administración.
Consulta información de clientes, ventas/facturas y permite agregar descuentos.
"""

from typing import Dict, List, Any, Optional
from datetime import date

from services.supabase_client import supabase


def get_all_clientes() -> List[Dict[str, Any]]:
    """
    Obtiene todos los clientes con información básica.
    Incluye joins con estado_cliente y tipo_documento para mostrar descripciones.
    """
    try:
        result = supabase.table("cliente").select(
            """
            id_cliente,
            nombre,
            correo,
            numero,
            documento,
            estado_cliente:estado_cliente_id(descripcion),
            tipo_documento:tipo_cliente_id(descripcion)
            """
        ).execute()
        print(f"[clientes_admin_service] fetched {len(result.data or [])} clientes")
        return result.data or []
    except Exception as exc:
        print(f"[clientes_admin_service] error fetching clientes: {exc}")
        import traceback
        traceback.print_exc()
        return []


def get_cliente_by_id(cliente_id: str) -> Optional[Dict[str, Any]]:
    """
    Obtiene información detallada de un cliente específico.
    """
    try:
        result = supabase.table("cliente").select(
            """
            id_cliente,
            nombre,
            correo,
            numero,
            documento,
            estado_cliente:estado_cliente_id(descripcion),
            tipo_documento:tipo_cliente_id(descripcion)
            """
        ).eq("id_cliente", cliente_id).execute()
        
        data = result.data or []
        return data[0] if data else None
    except Exception as exc:
        print(f"[clientes_admin_service] error fetching cliente {cliente_id}: {exc}")
        import traceback
        traceback.print_exc()
        return None


def get_cliente_ventas(cliente_id: str) -> List[Dict[str, Any]]:
    """
    Obtiene las ventas/facturas asociadas a un cliente.
    Se relaciona a través de registro_pago -> cliente_id
    """
    try:
        # Obtener registros de pago del cliente
        result = supabase.table("registro_pago").select(
            """
            id_registro,
            fecha,
            monto,
            documento,
            metodo_pago:metodo_pago_id(descripcion)
            """
        ).eq("cliente_id", cliente_id).order("fecha", desc=True).execute()
        
        print(f"[clientes_admin_service] fetched {len(result.data or [])} ventas for cliente {cliente_id}")
        return result.data or []
    except Exception as exc:
        print(f"[clientes_admin_service] error fetching ventas: {exc}")
        import traceback
        traceback.print_exc()
        return []


def add_cliente_descuento(cliente_id: str, descripcion: str, porcentaje: float) -> bool:
    """
    Agrega un descuento/promoción a un cliente.
    Nota: Como no existe tabla específica de descuentos en el schema,
    esto podría implementarse de varias formas:
    1. Crear una nueva tabla de descuentos
    2. Usar una tabla existente adaptada
    3. Almacenar en un campo JSON del cliente
    
    Por ahora, retornamos True como placeholder.
    En producción, deberías crear una tabla 'descuentos_cliente' con:
    - id_descuento (uuid)
    - cliente_id (uuid FK)
    - descripcion (varchar)
    - porcentaje (numeric)
    - fecha_inicio (date)
    - fecha_fin (date)
    - activo (boolean)
    """
    try:
        # Placeholder: En producción, insertar en tabla de descuentos
        # Por ahora solo logueamos
        print(f"[clientes_admin_service] adding descuento to cliente {cliente_id}: {descripcion} ({porcentaje}%)")
        
        # Ejemplo de inserción si existiera la tabla:
        # result = supabase.table("descuentos_cliente").insert({
        #     "cliente_id": cliente_id,
        #     "descripcion": descripcion,
        #     "porcentaje": porcentaje,
        #     "fecha_inicio": str(date.today()),
        #     "activo": True
        # }).execute()
        
        return True
    except Exception as exc:
        print(f"[clientes_admin_service] error adding descuento: {exc}")
        import traceback
        traceback.print_exc()
        return False


def get_clientes_stats() -> Dict[str, Any]:
    """
    Obtiene estadísticas generales de clientes.
    """
    try:
        # Total de clientes
        result = supabase.table("cliente").select("id_cliente", count="exact").execute()
        total = result.count or 0
        
        return {
            "total_clientes": total,
        }
    except Exception as exc:
        print(f"[clientes_admin_service] error fetching stats: {exc}")
        return {"total_clientes": 0}


__all__ = [
    "get_all_clientes",
    "get_cliente_by_id",
    "get_cliente_ventas",
    "add_cliente_descuento",
    "get_clientes_stats",
]
