"""
Servicio para finalizar entregas completas.
"""
import json
from typing import Dict, Any
from app.services.supabase_client import supabase
from app.services.entrega_productos_service import _obtener_carrito_id


def finalizar_entrega_completa(notificacion_id: str, cortes_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Finaliza entrega después de confirmar productos:
    1. Elimina cortes de tabla cortes
    2. Marca carrito como entregado
    3. Elimina notificación
    
    NOTA: Los productos ya fueron confirmados y eliminados de productos_carrito
    en el endpoint /api/entrega/productos/confirmar
    """
    try:
        if not notificacion_id:
            return {"success": False, "message": "ID de notificación requerido"}

        # 1. Obtener carrito_id
        carrito_id = _obtener_carrito_id(notificacion_id)
        if not carrito_id:
            return {"success": False, "message": "No se encontró carrito"}

        print(f"Finalizando entrega: notificacion_id={notificacion_id}, carrito_id={carrito_id}")

        # 2. Obtener cortes para contar
        cortes_cliente = []
        try:
            cortes_result = supabase.table("cortes") \
                .select("*") \
                .eq("carrito_id", carrito_id) \
                .execute()
            cortes_cliente = cortes_result.data or []
            print(f"Se encontraron {len(cortes_cliente)} cortes para eliminar")
        except Exception as e:
            print(f"Advertencia obtener cortes: {str(e)}")
            cortes_cliente = []

        # 3. Eliminar CORTES
        try:
            if cortes_cliente:
                supabase.table("cortes") \
                    .delete() \
                    .eq("carrito_id", carrito_id) \
                    .execute()
                print(f"Eliminados {len(cortes_cliente)} cortes")
        except Exception as e:
            print(f"Error eliminando cortes: {str(e)}")

        # 4. Actualizar carrito_compras a estado "entregado"
        try:
            supabase.table("carrito_compras") \
                .update({"estado": "entregado"}) \
                .eq("id_carrito", carrito_id) \
                .execute()
            print(f"Carrito {carrito_id} marcado como entregado")
        except Exception as e:
            print(f"Error actualizando carrito: {str(e)}")

        # 5. Eliminar NOTIFICACIÓN
        try:
            delete_result = supabase.table("notificacion") \
                .delete() \
                .eq("id_notificacion", notificacion_id) \
                .execute()
            print(f"Notificación {notificacion_id} eliminada. Filas afectadas: {len(delete_result.data) if delete_result.data else 0}")
        except Exception as e:
            print(f"Error eliminando notificación: {str(e)}")

        return {
            "success": True,
            "message": "Entrega finalizada correctamente",
            "cortes_eliminados": len(cortes_cliente)
        }

    except Exception as exc:
        print(f"Error general en finalizar_entrega_completa: {str(exc)}")
        return {
            "success": False,
            "message": str(exc)
        }

