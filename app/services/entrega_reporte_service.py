"""
Servicio para guardar reporte temporal de entrega.
"""
import json
import os
from typing import Dict, Any


def _ruta_reporte_tmp() -> str:
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    data_dir = os.path.join(base_dir, "data")
    os.makedirs(data_dir, exist_ok=True)
    return os.path.join(data_dir, "entrega_reporte_tmp.json")


def _leer_registros(archivo: str) -> list:
    if not os.path.exists(archivo):
        return []

    with open(archivo, "r", encoding="utf-8") as handle:
        contenido = handle.read().strip()
        if not contenido:
            return []
        return json.loads(contenido)


def _merge_listas(base: list, extra: list, clave: str) -> list:
    if not extra:
        return base

    if not base:
        return extra

    vistos = set()
    resultado = []
    for item in base + extra:
        valor = item.get(clave) if isinstance(item, dict) else None
        if valor is None:
            resultado.append(item)
            continue
        if valor in vistos:
            continue
        vistos.add(valor)
        resultado.append(item)
    return resultado


def guardar_reporte_temporal(reporte: Dict[str, Any]) -> Dict[str, Any]:
    """
    Guarda o actualiza el reporte en un archivo temporal JSON.

    Returns:
        dict con {success: bool, message?: str}
    """
    try:
        archivo = _ruta_reporte_tmp()
        registros = _leer_registros(archivo)

        notificacion_id = reporte.get("notificacion_id")
        if notificacion_id:
            actualizado = False
            for item in registros:
                if item.get("notificacion_id") == notificacion_id:
                    item["cliente"] = reporte.get("cliente") or item.get("cliente")
                    item["fecha"] = reporte.get("fecha") or item.get("fecha")
                    item["generado_en"] = reporte.get("generado_en") or item.get("generado_en")
                    item["cortes"] = _merge_listas(item.get("cortes", []), reporte.get("cortes", []), "id_corte")
                    item["mermas"] = _merge_listas(item.get("mermas", []), reporte.get("mermas", []), "id_merma")
                    item["productos"] = _merge_listas(item.get("productos", []), reporte.get("productos", []), "producto_id")
                    item["plancha_por_corte"] = _merge_listas(
                        item.get("plancha_por_corte", []),
                        reporte.get("plancha_por_corte", []),
                        "producto_id"
                    )
                    actualizado = True
                    break

            if not actualizado:
                registros.append(reporte)
        else:
            registros.append(reporte)

        with open(archivo, "w", encoding="utf-8") as handle:
            json.dump(registros, handle, ensure_ascii=False, indent=2)

        return {"success": True}
    except Exception as exc:
        return {"success": False, "message": str(exc)}


def obtener_reporte_temporal(notificacion_id: str) -> Dict[str, Any]:
    """
    Obtiene el reporte temporal por notificacion_id.
    """
    try:
        archivo = _ruta_reporte_tmp()
        registros = _leer_registros(archivo)
        for item in registros:
            if item.get("notificacion_id") == notificacion_id:
                return {"success": True, "data": item}

        return {"success": False, "message": "Reporte no encontrado"}
    except Exception as exc:
        return {"success": False, "message": str(exc)}
