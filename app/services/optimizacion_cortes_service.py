# -*- coding: utf-8 -*-
"""
Service: Optimización de Cortes
Gateway hacia el motor de optimización FastAPI (puerto 5003).
"""
from typing import List, Dict, Any, Optional, Tuple
import requests
import os
from services.supabase_client import supabase


# URL del backend de optimización
OPTIMIZATION_BACKEND_URL = os.getenv("OPTIMIZATION_BACKEND_URL", "http://localhost:5003")


def calcular_cortes_optimizados(
    productos: List[Dict[str, Any]],
    tipo_material: str = "vidrio",
    plancha_ancho: float = 300.0,
    plancha_alto: float = 300.0,
    barra_largo: float = 300.0,
    permitir_rotacion: bool = True,
    min_retazo: float = 20.0
) -> Dict[str, Any]:
    """
    Calcula la optimización de cortes llamando al backend de optimización.

    Args:
        productos: Lista de productos con {id, cantidad, ancho?, alto?, largo?}
        tipo_material: "vidrio" | "aluminio"
        plancha_ancho: Ancho de plancha para vidrio (cm)
        plancha_alto: Alto de plancha para vidrio (cm)
        barra_largo: Largo de barra para aluminio (cm)
        permitir_rotacion: Permitir rotar piezas en vidrio
        min_retazo: Largo mínimo de retazo útil para aluminio (cm)

    Returns:
        Diccionario con planchas/barras, cortes, retazos y eficiencia
    """
    try:
        if tipo_material.lower() == "vidrio":
            return _optimizar_vidrio(productos, plancha_ancho, plancha_alto, permitir_rotacion)
        elif tipo_material.lower() == "aluminio":
            return _optimizar_aluminio(productos, barra_largo, min_retazo)
        else:
            return {"success": False, "error": f"Tipo de material no soportado: {tipo_material}"}

    except Exception as e:
        print(f"Error calculando optimización: {e}")
        return {"success": False, "error": str(e)}


def _optimizar_vidrio(
    productos: List[Dict[str, Any]],
    plancha_ancho: float,
    plancha_alto: float,
    permitir_rotacion: bool
) -> Dict[str, Any]:
    """
    Llama al endpoint de optimización de vidrio.
    """
    try:
        # Transformar productos a formato de cortes
        cortes = []
        for p in productos:
            cantidad = int(p.get("cantidad", 1))
            ancho = float(p.get("ancho") or p.get("ancho_cm") or 0)
            alto = float(p.get("alto") or p.get("alto_cm") or 0)

            if ancho > 0 and alto > 0:
                cortes.append({
                    "id": str(p.get("id", "")),
                    "ancho": ancho,
                    "alto": alto,
                    "cantidad": cantidad
                })

        if not cortes:
            return {"success": False, "error": "No hay cortes válidos para optimizar"}

        # Llamar al backend de optimización
        response = requests.post(
            f"{OPTIMIZATION_BACKEND_URL}/api/opt/vidrio",
            json={
                "plancha_ancho": plancha_ancho,
                "plancha_alto": plancha_alto,
                "cortes": cortes,
                "permitir_rotacion": permitir_rotacion
            },
            timeout=30
        )

        if response.status_code == 200:
            return {"success": True, **response.json()}
        else:
            return {"success": False, "error": f"Error {response.status_code}: {response.text}"}

    except requests.exceptions.RequestException as e:
        return {"success": False, "error": f"Error conectando con backend de optimización: {str(e)}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _optimizar_aluminio(
    productos: List[Dict[str, Any]],
    barra_largo: float,
    min_retazo: float
) -> Dict[str, Any]:
    """
    Llama al endpoint de optimización de aluminio.
    """
    try:
        # Transformar productos a formato de cortes
        cortes = []
        for p in productos:
            cantidad = int(p.get("cantidad", 1))
            largo = float(p.get("largo") or p.get("largo_cm") or 0)

            if largo > 0:
                cortes.append({
                    "id": str(p.get("id", "")),
                    "largo": largo,
                    "cantidad": cantidad
                })

        if not cortes:
            return {"success": False, "error": "No hay cortes válidos para optimizar"}

        # Llamar al backend de optimización
        response = requests.post(
            f"{OPTIMIZATION_BACKEND_URL}/api/opt/aluminio",
            json={
                "barra_largo": barra_largo,
                "cortes": cortes,
                "min_retazo": min_retazo
            },
            timeout=30
        )

        if response.status_code == 200:
            return {"success": True, **response.json()}
        else:
            return {"success": False, "error": f"Error {response.status_code}: {response.text}"}

    except requests.exceptions.RequestException as e:
        return {"success": False, "error": f"Error conectando con backend de optimización: {str(e)}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def generar_pdf_cortes(
    productos: List[Dict[str, Any]],
    plancha_ancho: float = 300.0,
    plancha_alto: float = 300.0,
    permitir_rotacion: bool = True,
    cliente: Optional[str] = None,
    referencia: Optional[str] = None,
) -> Optional[bytes]:
    """
    Genera un PDF de reporte de optimización de cortes de vidrio.
    Llama a POST /api/opt/vidrio/pdf en el backend de optimización.
    """
    try:
        cortes = []
        for p in productos:
            cantidad = int(p.get("cantidad", 1))
            ancho = float(p.get("ancho") or p.get("ancho_cm") or 0)
            alto = float(p.get("alto") or p.get("alto_cm") or 0)
            if ancho > 0 and alto > 0:
                cortes.append({
                    "id": str(p.get("id", "")),
                    "ancho": ancho,
                    "alto": alto,
                    "cantidad": cantidad,
                })

        if not cortes:
            return None

        response = requests.post(
            f"{OPTIMIZATION_BACKEND_URL}/api/opt/vidrio/pdf",
            json={
                "plancha_ancho": plancha_ancho,
                "plancha_alto": plancha_alto,
                "cortes": cortes,
                "permitir_rotacion": permitir_rotacion,
                "cliente": cliente,
                "referencia": referencia,
            },
            timeout=60,
        )

        if response.status_code == 200:
            return response.content
        return None

    except Exception as e:
        print(f"Error generando PDF: {e}")
        return None


def get_retasos_inventario() -> List[Dict[str, Any]]:
    """
    Obtiene los retazos disponibles en inventario.
    
    Returns:
        Lista de retazos con sus dimensiones y ubicación
    """
    try:
        # TODO: Consultar tabla de retazos
        result = supabase.table("retazos").select("*").eq("disponible", True).execute()
        return result.data or []
    
    except Exception as e:
        print(f"Error obteniendo retazos: {e}")
        return []


def guardar_optimizacion_cortes(data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Guarda los resultados de una optimización de cortes.
    
    Args:
        data: Datos de la optimización
    
    Returns:
        Datos guardados o None si falla
    """
    try:
        optimizacion_data = {
            "cliente": data.get("cliente"),
            "fecha": data.get("fecha"),
            "productos_seleccionados": data.get("productos_seleccionados", []),
            "barras": data.get("barras", []),
            "cortes": data.get("cortes", []),
            "plancha_aluminio": data.get("plancha_aluminio"),
            "estado": "PENDIENTE"
        }
        
        result = supabase.table("optimizaciones").insert(optimizacion_data).execute()
        return result.data[0] if result.data else None
    
    except Exception as e:
        print(f"Error guardando optimización: {e}")
        return None


def get_optimizacion_by_id(optimizacion_id: str) -> Optional[Dict[str, Any]]:
    """
    Obtiene el detalle de una optimización por ID.
    
    Args:
        optimizacion_id: ID de la optimización
    
    Returns:
        Datos de la optimización o None si no existe
    """
    try:
        result = supabase.table("optimizaciones").select("*").eq("id", optimizacion_id).execute()
        return result.data[0] if result.data else None
    
    except Exception as e:
        print(f"Error obteniendo optimización: {e}")
        return None


def _algoritmo_guillotina(ancho_plancha: float, alto_plancha: float, productos: List[Tuple[float, float]]) -> List[Dict[str, Any]]:
    """
    Algoritmo de corte tipo guillotina para optimización.
    (Implementación básica - mejorar según necesidades)
    
    Args:
        ancho_plancha: Ancho de la plancha en cm
        alto_plancha: Alto de la plancha en cm
        productos: Lista de tuplas (ancho, alto) de productos a cortar
    
    Returns:
        Lista de posiciones de corte
    """
    # TODO: Implementar algoritmo de guillotina
    # Esta es una función auxiliar para el cálculo de optimización
    return []
