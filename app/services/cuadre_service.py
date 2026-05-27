"""
Servicio para resumen mensual (Cuadre).
Agrupa pagos (pago), gastos, caja e ingresos por ventas.
"""

from typing import Dict, List, Any, Optional, Tuple
from datetime import date, datetime

from services.supabase_client import supabase


def _month_range(mes: str) -> Tuple[str, str]:
    """Devuelve primer y ultimo dia del mes en formato YYYY-MM-DD."""
    # mes esperado: YYYY-MM
    year, month = map(int, mes.split("-"))
    first_day = date(year, month, 1)
    # ultimo dia: ir al mes siguiente y restar 1 dia
    if month == 12:
        next_month = date(year + 1, 1, 1)
    else:
        next_month = date(year, month + 1, 1)
    last_day = next_month.fromordinal(next_month.toordinal() - 1)
    return (first_day.isoformat(), last_day.isoformat())


def get_pagos_by_month(mes: str) -> List[Dict[str, Any]]:
    ini, fin = _month_range(mes)
    try:
        result = supabase.table("pago").select("id_pago, monto, fecha").gte("fecha", ini).lte("fecha", fin).execute()
        return result.data or []
    except Exception as exc:
        print(f"[cuadre_service] error pagos: {exc}")
        return []


def get_gastos_by_month(mes: str) -> List[Dict[str, Any]]:
    ini, fin = _month_range(mes)
    try:
        result = supabase.table("gastos").select("id_gasto, monto, fecha, tipo").gte("fecha", ini).lte("fecha", fin).execute()
        return result.data or []
    except Exception as exc:
        print(f"[cuadre_service] error gastos: {exc}")
        return []


def get_caja_by_month(mes: str) -> List[Dict[str, Any]]:
    ini, fin = _month_range(mes)
    try:
        result = supabase.table("caja").select("id_caja, fecha, turno, subtotal").gte("fecha", ini).lte("fecha", fin).execute()
        return result.data or []
    except Exception as exc:
        print(f"[cuadre_service] error caja: {exc}")
        return []


def get_ventas_by_month(mes: str) -> List[Dict[str, Any]]:
    ini, fin = _month_range(mes)
    try:
        result = supabase.table("venta").select("id_venta, total, fecha_venta, caja_id, metodo").gte("fecha_venta", ini).lte("fecha_venta", fin).execute()
        return result.data or []
    except Exception as exc:
        print(f"[cuadre_service] error ventas: {exc}")
        return []


def get_resumen_mes(mes: str) -> Dict[str, Any]:
    gastos = get_gastos_by_month(mes)
    cajas = get_caja_by_month(mes)
    ventas = get_ventas_by_month(mes)

    total_gastos = sum(float(g.get("monto", 0) or 0) for g in gastos)
    # Monto en caja = suma de subtotales de los registros de tabla caja del mes seleccionado
    total_ingresos_caja = sum(float(c.get("subtotal") or 0) for c in cajas)
    total_ventas = sum(float(v.get("total", 0) or 0) for v in ventas)

    ingreso = total_ingresos_caja
    egreso = total_gastos
    total_empresa = ingreso - egreso

    # Monto real de empresa: saldo actual en tabla pago (registro unico/ultimo)
    monto_empresa_real = 0.0
    try:
        pago_actual = (
            supabase.table("pago")
            .select("monto, fecha")
            .order("fecha", desc=True)
            .limit(1)
            .execute()
        )
        rows = pago_actual.data or []
        if rows:
            monto_empresa_real = float(rows[0].get("monto") or 0)
    except Exception as exc:
        print(f"[cuadre_service] error monto real empresa: {exc}")

    # Sumar ventas por metodo
    totales_por_metodo = get_totales_por_metodo_venta(ventas)
    return {
        "mes": mes,
        "gastos": gastos,
        "cajas": cajas,
        "ventas": ventas,
        "ingreso": ingreso,
        "egreso": egreso,
        "monto_en_caja": total_ingresos_caja,
        "monto_empresa": total_empresa,
        "monto_empresa_real": monto_empresa_real,
        "totales_por_metodo": totales_por_metodo,
    }


def get_totales_por_metodo_venta(ventas: List[Dict[str, Any]]) -> Dict[str, float]:
    """Suma los totales de ventas agrupados por metodo de pago."""
    def _normalizar_metodo(raw: Any) -> str:
        metodo = " ".join(str(raw or "").strip().lower().split())
        if not metodo:
            return ""
        if metodo in {"tarjeta", "por tarjeta", "credito", "debito", "debito"}:
            return "tarjeta"
        if metodo in {"yape", "por yape"}:
            return "yape"
        if metodo in {"efectivo", "contado", "al contado"}:
            return "contado"
        return metodo

    totales = {}
    for v in ventas:
        metodo = _normalizar_metodo(v.get("metodo"))
        total = float(v.get("total") or 0)
        if metodo:
            totales[metodo] = totales.get(metodo, 0) + total
    return totales


def get_pagos_listado(mes: str) -> List[Dict[str, Any]]:
    """Combina gastos y caja en un solo listado con tipo. La tabla pago
    representa el saldo acumulado de la empresa (no gastos mensuales)
    y se excluye del listado para evitar confusion con EGRESO."""
    gastos_rows = [{
        "tipo": g.get("tipo") or "gasto",
        "id": g.get("id_gasto"),
        "fecha": g.get("fecha"),
        "monto": g.get("monto"),
        "codigo": (g.get("id_gasto") or "")[:8]
    } for g in get_gastos_by_month(mes)]

    listado = gastos_rows
    try:
        listado.sort(key=lambda x: x.get("fecha") or "")
    except Exception:
        pass
    return listado


__all__ = [
    "get_resumen_mes",
    "get_pagos_listado",
]