# -*- coding: utf-8 -*-
"""
Servicio de Integración con Backend de Reconocimiento de Imágenes

Responsabilidad:
- Llamar al backend de reconocimiento
- Procesar respuestas
- Manejo de errores
"""
import logging
import os
import requests
import base64
from typing import Dict, Any, Optional
import asyncio

logger = logging.getLogger(__name__)


class ImagenProcesimientoService:
    """
    Servicio que integra con Backend Reconocimiento de Imágenes.

    Flujo:
    1. Recibe imagen en bytes
    2. Llama a backend reconocimiento en puerto 5001
    3. Recibe imagen procesada + metadata
    4. Retorna al cliente (guardará en Supabase)
    """

    def __init__(self):
        """Inicializa el servicio con URL del backend de reconocimiento"""
        self.backend_reconocimiento_url = os.getenv(
            "BACKEND_RECONOCIMIENTO_URL",
            "http://localhost:5001"
        )
        self.timeout = int(os.getenv("RECONOCIMIENTO_TIMEOUT", 30))

        logger.info(f"✓ ImagenProcesimientoService inicializado")
        logger.info(f"  Backend reconocimiento: {self.backend_reconocimiento_url}")

    def _verificar_backend_disponible(self) -> bool:
        """Verifica que el backend de reconocimiento esté disponible"""
        try:
            response = requests.get(
                f"{self.backend_reconocimiento_url}/ping",
                timeout=5
            )
            disponible = response.status_code == 200
            if disponible:
                logger.info("✓ Backend reconocimiento disponible")
            else:
                logger.warning(f"⚠ Backend reconocimiento respondió con {response.status_code}")
            return disponible
        except Exception as e:
            logger.error(f"✗ Backend reconocimiento no disponible: {str(e)}")
            return False

    def procesar_imagen_optimizada_desde_bytes(
        self,
        imagen_bytes: bytes,
        tamaño_salida: int = 512,
        confianza_minima: float = 0.5,
        categoria: str = 'otro'
    ) -> Dict[str, Any]:
        """
        Procesa imagen OPTIMIZADA: detecta objeto, recorta, elimina fondo, normaliza.

        Args:
            imagen_bytes: Bytes de la imagen
            tamaño_salida: Tamaño final (512, 768, 1024)
            confianza_minima: Score mínimo para detección YOLO
            categoria: Tipo de producto ('vidrio', 'aluminio', 'accesorio', 'otro')

        Returns:
            {
                "success": bool,
                "data": {
                    "imagen_optimizada": "base64",
                    "imagen_size": "512x512",
                    "objeto_detectado": bool,
                    "clasificacion": {...},
                    "tiempo_procesamiento": float
                }
            }
        """
        try:
            if not self._verificar_backend_disponible():
                return {
                    "success": False,
                    "error": "Backend de reconocimiento no disponible",
                    "data": None
                }

            logger.info(f"Procesando imagen optimizada ({len(imagen_bytes)} bytes, categoría={categoria}, tamaño={tamaño_salida})")

            # Preparar datos para POST con content-type
            content_type = "image/jpeg"
            if imagen_bytes.startswith(b'\x89PNG'):
                content_type = "image/png"
            elif imagen_bytes.startswith(b'\xFF\xD8\xFF'):
                content_type = "image/jpeg"
            elif imagen_bytes.startswith(b'GIF8'):
                content_type = "image/gif"

            files = {"file": ("imagen.jpg", imagen_bytes, content_type)}
            params = {
                "confianza_minima": confianza_minima,
                "tamaño_salida": tamaño_salida,
                "categoria": categoria,  # Pasar categoría
            }

            # Llamar al nuevo endpoint optimizado
            response = requests.post(
                f"{self.backend_reconocimiento_url}/api/procesar/imagen-optimizada",
                files=files,
                params=params,
                timeout=self.timeout
            )

            if response.status_code == 200:
                resultado = response.json()
                logger.info(f"✓ Imagen optimizada correctamente")
                logger.info(f"  Tiempo procesamiento: {resultado['data'].get('tiempo_procesamiento', 'N/A')}s")
                return resultado
            else:
                error_msg = response.text
                logger.error(f"✗ Error backend reconocimiento: {response.status_code}")
                logger.error(f"  Detalle: {error_msg}")
                return {
                    "success": False,
                    "error": f"Error {response.status_code}: {error_msg}",
                    "data": None
                }

        except requests.exceptions.Timeout:
            logger.error(f"✗ Timeout en backend reconocimiento (>{self.timeout}s)")
            return {
                "success": False,
                "error": f"Timeout procesando imagen (máximo {self.timeout}s)",
                "data": None
            }
        except Exception as e:
            logger.error(f"✗ Error comunicando con backend reconocimiento: {str(e)}")
            return {
                "success": False,
                "error": f"Error de comunicación: {str(e)}",
                "data": None
            }

    def procesar_imagen_desde_bytes(
        self,
        imagen_bytes: bytes,
        incluir_segmentacion: bool = True,
        incluir_clasificacion: bool = True,
        confianza_minima: float = 0.5
    ) -> Dict[str, Any]:
        """
        Procesa una imagen llamando al backend de reconocimiento.

        Args:
            imagen_bytes: Bytes de la imagen
            incluir_segmentacion: ¿Ejecutar YOLO?
            incluir_clasificacion: ¿Ejecutar ResNet50?
            confianza_minima: Score mínimo para detecciones

        Returns:
            Diccionario con:
            {
                "success": bool,
                "data": {
                    "imagen_sin_fondo": "base64",
                    "segmentacion": {...},
                    "clasificacion": {...},
                    "tiempo_procesamiento": float
                },
                "error": str (si falla)
            }
        """
        try:
            # Verificar que el backend esté disponible
            if not self._verificar_backend_disponible():
                return {
                    "success": False,
                    "error": "Backend de reconocimiento no disponible",
                    "data": None
                }

            logger.info(f"Enviando imagen al backend de reconocimiento ({len(imagen_bytes)} bytes)")

            # Preparar datos para POST con content-type
            # Detectar formato basado en signature (magic bytes)
            content_type = "image/jpeg"  # default
            if imagen_bytes.startswith(b'\x89PNG'):
                content_type = "image/png"
            elif imagen_bytes.startswith(b'\xFF\xD8\xFF'):
                content_type = "image/jpeg"
            elif imagen_bytes.startswith(b'GIF8'):
                content_type = "image/gif"

            files = {"file": ("imagen.jpg", imagen_bytes, content_type)}
            params = {
                "incluir_segmentacion": incluir_segmentacion,
                "incluir_clasificacion": incluir_clasificacion,
                "confianza_minima": confianza_minima,
            }

            # Llamar al backend de reconocimiento
            response = requests.post(
                f"{self.backend_reconocimiento_url}/api/procesar/imagen",
                files=files,
                params=params,
                timeout=self.timeout
            )

            # Procesar respuesta
            if response.status_code == 200:
                resultado = response.json()
                logger.info(f"✓ Imagen procesada correctamente")
                logger.info(f"  Tiempo procesamiento: {resultado['data'].get('tiempo_procesamiento', 'N/A')}s")
                return resultado
            else:
                error_msg = response.text
                logger.error(f"✗ Error backend reconocimiento: {response.status_code}")
                logger.error(f"  Detalle: {error_msg}")
                return {
                    "success": False,
                    "error": f"Error {response.status_code}: {error_msg}",
                    "data": None
                }

        except requests.exceptions.Timeout:
            logger.error(f"✗ Timeout en backend reconocimiento (>{self.timeout}s)")
            return {
                "success": False,
                "error": f"Timeout procesando imagen (máximo {self.timeout}s)",
                "data": None
            }
        except Exception as e:
            logger.error(f"✗ Error comunicando con backend reconocimiento: {str(e)}")
            return {
                "success": False,
                "error": f"Error de comunicación: {str(e)}",
                "data": None
            }

    def procesar_imagen_desde_base64(
        self,
        imagen_base64: str,
        incluir_segmentacion: bool = True,
        incluir_clasificacion: bool = True,
        confianza_minima: float = 0.5
    ) -> Dict[str, Any]:
        """
        Procesa imagen desde base64.

        Args:
            imagen_base64: String con imagen en base64
            incluir_segmentacion: ¿Ejecutar YOLO?
            incluir_clasificacion: ¿Ejecutar ResNet50?
            confianza_minima: Score mínimo

        Returns:
            Resultado del procesamiento
        """
        try:
            imagen_bytes = base64.b64decode(imagen_base64)
            return self.procesar_imagen_desde_bytes(
                imagen_bytes,
                incluir_segmentacion=incluir_segmentacion,
                incluir_clasificacion=incluir_clasificacion,
                confianza_minima=confianza_minima
            )
        except Exception as e:
            logger.error(f"✗ Error decodificando base64: {str(e)}")
            return {
                "success": False,
                "error": f"Error decodificando imagen: {str(e)}",
                "data": None
            }

    def solo_eliminar_fondo(self, imagen_bytes: bytes) -> Dict[str, Any]:
        """
        Solo elimina fondo (más rápido).

        Args:
            imagen_bytes: Bytes de la imagen

        Returns:
            {
                "success": bool,
                "data": {
                    "imagen_sin_fondo": "base64",
                    "metadata": {...}
                }
            }
        """
        try:
            if not self._verificar_backend_disponible():
                return {
                    "success": False,
                    "error": "Backend no disponible",
                    "data": None
                }

            files = {"file": ("imagen.jpg", imagen_bytes, "image/jpeg")}
            response = requests.post(
                f"{self.backend_reconocimiento_url}/api/procesar/fondo",
                files=files,
                timeout=self.timeout
            )

            if response.status_code == 200:
                logger.info("✓ Fondo eliminado correctamente")
                return response.json()
            else:
                logger.error(f"✗ Error eliminando fondo: {response.status_code}")
                return {
                    "success": False,
                    "error": response.text,
                    "data": None
                }

        except Exception as e:
            logger.error(f"✗ Error: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "data": None
            }
