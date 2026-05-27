# -*- coding: utf-8 -*-
"""
Service: Diseño de Servicios
Gateway hacia el motor de diseño en backend-optimizacion (puerto 5003).
Calcula el diseño completo de ventanas, puertas, mamparas y otros servicios:
cortes de aluminio, paneles de vidrio y posiciones geométricas para el blueprint SVG.
"""
from typing import Dict, Any, Optional
import requests
import os

OPTIMIZATION_BACKEND_URL = os.getenv("OPTIMIZATION_BACKEND_URL", "http://localhost:5003")


def calcular_diseno_servicio(
    nombre_servicio: str,
    ancho: float,
    alto: float,
    tipo: Optional[str] = None,
    barra_largo: float = 300.0,
    plancha_ancho: float = 300.0,
    plancha_alto: float = 300.0,
) -> Dict[str, Any]:
    """
    Llama a POST /api/opt/diseno en backend-optimizacion.
    Devuelve el diseño completo del servicio:
      - aluminio: cortes, distribución en barras, totales
      - vidrio: paneles, uso de plancha, áreas
      - diseno: posiciones geométricas en cm para el blueprint SVG del frontend
    """
    try:
        payload: Dict[str, Any] = {
            "nombre_servicio": nombre_servicio,
            "ancho":           ancho,
            "alto":            alto,
            "barra_largo":     barra_largo,
            "plancha_ancho":   plancha_ancho,
            "plancha_alto":    plancha_alto,
        }
        if tipo:
            payload["tipo"] = tipo

        response = requests.post(
            f"{OPTIMIZATION_BACKEND_URL}/api/opt/diseno",
            json=payload,
            timeout=15,
        )

        if response.status_code == 200:
            return {"success": True, **response.json()}
        return {
            "success": False,
            "error": f"Error {response.status_code}: {response.text}",
        }

    except requests.exceptions.ConnectionError:
        return {"success": False, "error": "No se pudo conectar con el motor de diseño (puerto 5003)"}
    except requests.exceptions.Timeout:
        return {"success": False, "error": "El motor de diseño tardó demasiado en responder"}
    except Exception as e:
        return {"success": False, "error": str(e)}
