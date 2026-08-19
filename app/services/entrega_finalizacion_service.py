"""
Servicio para finalizar entregas completas.
"""
import json
import threading
import time
from typing import Dict, Any
from app.services.supabase_client import supabase
from app.services.entrega_productos_service import _obtener_carrito_id

# Tiempo que el cliente ve la barra en "Entregado" (100%) antes de que
# desaparezca, igual al timer que ya usaba el frontend.
_DELAY_LIMPIEZA_SEGUNDOS = 60


def _eliminar_carrito_diferido(carrito_id: str, delay_seconds: int = _DELAY_LIMPIEZA_SEGUNDOS) -> None:
    """Espera el delay y luego elimina el carrito (la barra del cliente desaparece)."""
    try:
        time.sleep(delay_seconds)
        # venta.carrito_id tiene FK hacia carrito_compras: primero se
        # desvincula la venta (se conserva, solo pierde el carrito_id).
        supabase.table("venta").update({"carrito_id": None}).eq("carrito_id", carrito_id).execute()
        supabase.table("carrito_compras").delete().eq("id_carrito", carrito_id).execute()
        print(f"[LIMPIEZA DIFERIDA] Carrito {carrito_id} eliminado tras {delay_seconds}s")
    except Exception as e:
        print(f"[LIMPIEZA DIFERIDA] Error eliminando carrito {carrito_id}: {e}")


def finalizar_entrega_completa(notificacion_id: str, cortes_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Finaliza entrega después de confirmar productos:
    1. Elimina cortes de tabla cortes
    2. Marca el carrito como "entregado" (el cliente ve la barra al 100%)
    3. Elimina notificación
    4. Programa la eliminación del carrito tras un delay (la barra desaparece)

    NOTA: Los productos ya fueron confirmados y el historial queda en venta.
    """
    try:
        if not notificacion_id:
            return {"success": False, "message": "ID de notificación requerido"}

        # 1. Obtener carrito_id
        carrito_id = _obtener_carrito_id(notificacion_id)
        if not carrito_id:
            return {"success": False, "message": "No se encontró carrito"}

        print(f"Finalizando entrega: notificacion_id={notificacion_id}, carrito_id={carrito_id}")

        # 2. Obtener cortes para contar — 'cortes' ya no tiene carrito_id propio,
        # se relaciona vía venta_id (venta.carrito_id -> venta.id_venta -> cortes.venta_id).
        cortes_cliente = []
        try:
            ventas_result = supabase.table("venta") \
                .select("id_venta") \
                .eq("carrito_id", carrito_id) \
                .execute()
            venta_ids = [v.get("id_venta") for v in (ventas_result.data or []) if v.get("id_venta")]

            if venta_ids:
                cortes_result = supabase.table("cortes") \
                    .select("*") \
                    .in_("venta_id", venta_ids) \
                    .execute()
                cortes_cliente = cortes_result.data or []
            print(f"Se encontraron {len(cortes_cliente)} cortes para eliminar")
        except Exception as e:
            print(f"Advertencia obtener cortes: {str(e)}")
            cortes_cliente = []
            venta_ids = []

        # 3. Eliminar CORTES
        try:
            if cortes_cliente and venta_ids:
                supabase.table("cortes") \
                    .delete() \
                    .in_("venta_id", venta_ids) \
                    .execute()
                print(f"Eliminados {len(cortes_cliente)} cortes")
        except Exception as e:
            print(f"Error eliminando cortes: {str(e)}")

        # 4. Marcar carrito_compras como "entregado" -- si esto falla o no
        # afecta ninguna fila, NO seguir (la notificacion quedaria borrada
        # pero el carrito nunca pasaria a "Entregado" para el cliente, y sin
        # la notificacion ya no habria forma de reintentar).
        try:
            upd = supabase.table("carrito_compras") \
                .update({"estado": "entregado"}) \
                .eq("id_carrito", carrito_id) \
                .execute()
            if not getattr(upd, "data", None):
                return {
                    "success": False,
                    "message": f"No se pudo marcar el carrito {carrito_id} como entregado (no se encontro la fila)."
                }
            print(f"Carrito {carrito_id} marcado como entregado")
        except Exception as e:
            print(f"Error actualizando carrito: {str(e)}")
            return {"success": False, "message": f"Error actualizando carrito: {str(e)}"}

        # 5. Eliminar NOTIFICACIÓN
        try:
            delete_result = supabase.table("notificacion") \
                .delete() \
                .eq("id_notificacion", notificacion_id) \
                .execute()
            print(f"Notificación {notificacion_id} eliminada. Filas afectadas: {len(delete_result.data) if delete_result.data else 0}")
        except Exception as e:
            print(f"Error eliminando notificación: {str(e)}")

        # 6. Programar limpieza del carrito (borrado diferido en backend, no
        # depende de que el navegador del cliente siga abierto).
        try:
            threading.Thread(
                target=_eliminar_carrito_diferido,
                args=(carrito_id,),
                daemon=True,
            ).start()
        except Exception as e:
            print(f"No se pudo programar limpieza diferida del carrito {carrito_id}: {e}")

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

