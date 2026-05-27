"""
Servicio para mÃ©tricas del dashboard (IA).
Consulta Supabase para obtener conteos bÃ¡sicos que el frontend puede consumir.
"""

from typing import Dict

from services.supabase_client import supabase

# Tabla -> (nombre_tabla, columna_id)
TABLE_MAP = {
    "servicios": ("servicio", "id_servicio"),
    "productos": ("productos", "id_producto"),
    "clientes": ("cliente", "id_cliente"),
    "pedidos": ("notificacion", "id_notificacion"),
}


def _count_table(table: str, id_col: str) -> int:
    try:
        result = supabase.table(table).select(id_col, count="exact").execute()
        if hasattr(result, "count") and result.count is not None:
            return int(result.count)
        return len(result.data or [])
    except Exception as exc:  # noqa: BLE001
        print(f"[ai_dashboard_service] error counting {table}: {exc}")
        return 0


def get_dashboard_counts() -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for key, (table, col) in TABLE_MAP.items():
        counts[key] = _count_table(table, col)
    return counts


__all__ = ["get_dashboard_counts"]

