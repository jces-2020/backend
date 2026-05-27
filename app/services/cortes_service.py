from typing import Dict, List, Any

COSTO_CORTE = 10.0


def es_material_aluminio(producto: Dict[str, Any]) -> bool:
    texto = " ".join([
        str(producto.get("nombre") or ""),
        str(producto.get("descripcion") or ""),
        str(producto.get("categoria") or ""),
    ]).upper()
    return "ALUMIN" in texto


def calcular_total_corte(corte: Dict[str, Any], precio_unitario: float, es_aluminio: bool = False) -> float:
    ancho = float(corte.get("ancho_cm") or 0)
    alto = float(corte.get("alto_cm") or 0)
    cantidad = float(corte.get("cantidad") or 0)

    if ancho <= 0 or cantidad <= 0:
        return 0.0

    if es_aluminio:
        longitud_m = ancho / 100.0
        precio_base = longitud_m * float(precio_unitario or 0)
        return round((precio_base + COSTO_CORTE) * cantidad, 2)

    if alto <= 0:
        return 0.0

    area_cm2 = ancho * alto
    area_m2 = area_cm2 / 10000.0
    precio_base = area_m2 * float(precio_unitario or 0)
    return round((precio_base + COSTO_CORTE) * cantidad, 2)


def calcular_precio_cortes(
    cortes: List[Dict[str, Any]],
    precio_unitario: float,
    es_aluminio: bool = False,
) -> Dict[str, Any]:
    """Calcula el precio total por cortes.

    Formula:
    area_cm2 = ancho * alto
    area_m2 = area_cm2 / 10000
    precio_base = area_m2 * precio_unitario
    mano_obra = COSTO_CORTE
    precio_corte = (area_m2 * precio_base + mano_obra) * cantidad
    """
    detalle = []
    total = 0.0

    for corte in cortes or []:
        ancho = float(corte.get("ancho_cm") or 0)
        alto = float(corte.get("alto_cm") or 0)
        cantidad = float(corte.get("cantidad") or 0)
        if ancho <= 0 or cantidad <= 0:
            continue

        area_m2 = 0.0
        if not es_aluminio:
            if alto <= 0:
                continue
            area_cm2 = ancho * alto
            area_m2 = area_cm2 / 10000.0

        precio_corte = calcular_total_corte(corte, precio_unitario, es_aluminio)

        detalle.append({
            "ancho_cm": ancho,
            "alto_cm": alto,
            "cantidad": cantidad,
            "area_m2": round(area_m2, 4),
            "precio_corte": round(precio_corte, 2)
        })
        total += precio_corte

    return {
        "total": round(total, 2),
        "detalle": detalle,
        "costo_corte": COSTO_CORTE
    }
