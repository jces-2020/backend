"""
Servicio para finalizar y guardar servicios tÃ©cnicos completados.
Gestiona: upload foto â†’ tabla servicio â†’ estado instalado temporal â†’ limpieza diferida
"""
from typing import Optional, Dict, Any, Tuple
import threading
import time
from services.supabase_client import supabase


def guardar_servicio_completado(
    carrito_id: Optional[str],
    cliente_id: str,
    notif_id: Optional[str],
    nombre_servicio: str,
    descripcion: str,
    archivo_foto: Any,
    cleanup_inmediata: bool = False,
) -> Tuple[bool, str, Optional[str]]:
    """
    Guarda un servicio completado con foto y realiza limpieza.
    
    Args:
        carrito_id: UUID del carrito del servicio
        cliente_id: UUID del cliente (para buscar cortes/notificaciÃ³n)
        nombre_servicio: Nombre del servicio (ej: "Cristal de 2.5mm")
        descripcion: DescripciÃ³n/observaciones de instalaciÃ³n
        archivo_foto: Archivo de foto desde request.files
    
    Returns:
        Tupla: (success: bool, message: str, foto_url: Optional[str])
    """
    try:
        print(f"\n[SERVICIO] Iniciando guardar_servicio_completado")
        print(f"  carrito_id: {carrito_id}")
        print(f"  cliente_id: {cliente_id}")
        print(f"  nombre_servicio: {nombre_servicio}")
        
        # Resolver carrito_id si no vino desde frontend
        carrito_id_final = carrito_id
        if not carrito_id_final:
            carrito_id_final = _resolver_carrito_servicio(cliente_id)
            print(f"[SERVICIO] carrito_id resuelto por cliente: {carrito_id_final}")

        # 1. Subir foto a Supabase Storage
        print("[SERVICIO] Paso 1: Subiendo foto...")
        foto_url = None
        if archivo_foto and archivo_foto.filename:
            foto_url = _subir_foto_servicio(carrito_id_final or cliente_id, archivo_foto)
            if not foto_url:
                print("[ERROR] No se pudo subir la foto")
                return False, "Error al subir foto a Storage", None
            print(f"[SUCCESS] Foto subida: {foto_url}")
        
        # 2. Guardar servicio en tabla
        print("[SERVICIO] Paso 2: Guardando en tabla servicio...")
        servicio_data = {
            "nombre": nombre_servicio,
            "descripcion": descripcion,
            "ING": foto_url or ""  # Usando ING como campo de URL temporal
        }
        
        print(f"  Datos a insertar: {servicio_data}")
        servicio_result = supabase.table("servicio").insert(servicio_data).execute()
        if not servicio_result.data:
            print("[ERROR] Error al insertar en tabla servicio")
            return False, "Error al guardar servicio en BD", foto_url
        print(f"[SUCCESS] Servicio guardado: {servicio_result.data}")
        
        # 3. Marcar carrito como INSTALADO (visible en PanelCliente)
        print("[SERVICIO] Paso 3: Marcando carrito como INSTALADO...")
        if carrito_id_final:
            try:
                supabase.table("carrito_compras") \
                    .update({"estado": "instalado"}) \
                    .eq("id_carrito", carrito_id_final) \
                    .execute()
                print("[SUCCESS] Carrito marcado como INSTALADO")
            except Exception as e:
                print(f"[WARN] Error actualizando estado a instalado: {e}")
        else:
            print("  Sin carrito_id, no se pudo marcar estado INSTALADO")

        # 4. Limpieza de carrito/cortes
        if carrito_id_final:
            if cleanup_inmediata:
                print("[SERVICIO] Paso 4: Programando limpieza diferida en 60 segundos (esperar estado Instalado)...")
                _programar_limpieza_diferida(carrito_id_final, delay_seconds=60)
                print("[SUCCESS] Limpieza diferida en 60s programada")
            else:
                print("[SERVICIO] Paso 4: Programando limpieza diferida en 10 minutos...")
                _programar_limpieza_diferida(carrito_id_final, delay_seconds=600)
                print("[SUCCESS] Limpieza diferida programada")
        else:
            print("  Sin carrito_id, no se pudo limpiar carrito/cortes")
        
        # 5. Eliminar notificaciÃ³n asociada
        print("[SERVICIO] Paso 5: Eliminando notificaciÃ³n...")
        try:
            eliminadas = 0

            # Intentar eliminar por ID exacto (fuente principal del panel de obras)
            if notif_id:
                try:
                    supabase.table("notificacion").delete().eq("id_notificacion", notif_id).execute()
                    eliminadas += 1
                    print(f"  NotificaciÃ³n eliminada por notif_id en tabla 'notificacion': {notif_id}")
                except Exception as e:
                    print(f"  [WARN] No se pudo eliminar notif_id en 'notificacion': {e}")

                # Fallback histÃ³rico
                try:
                    supabase.table("notificacion").delete().eq("id_notificacion", notif_id).execute()
                    print(f"  Intento de limpieza en tabla 'notificacion' para notif_id: {notif_id}")
                except Exception:
                    pass

            # Fallback por cliente + tipo SERVICIO
            tipos_servicio = ["SERVICIO", "servicio"]
            for t in tipos_servicio:
                try:
                    res_notif = supabase.table("notificacion") \
                        .select("id_notificacion") \
                        .eq("id_cliente", cliente_id) \
                        .eq("tipo", t) \
                        .execute()
                    for n in (res_notif.data or []):
                        supabase.table("notificacion").delete().eq("id_notificacion", n.get("id_notificacion")).execute()
                        eliminadas += 1
                except Exception:
                    pass

            print(f"[SUCCESS] Limpieza de notificaciones completada. Eliminadas: {eliminadas}")
        except Exception as e:
            print(f"[WARN] Error eliminando notificaciÃ³n: {e}")
        
        print("[SUCCESS] guardar_servicio_completado finalizado exitosamente\n")
        if cleanup_inmediata:
            return True, "Servicio finalizado correctamente. Estado Instalado por 1 minuto.", foto_url
        return True, "Servicio guardado exitosamente. Estado INSTALADO por 10 minutos", foto_url
    
    except Exception as e:
        print(f"[ERROR] en guardar_servicio_completado: {e}")
        import traceback
        traceback.print_exc()
        return False, f"Error: {str(e)}", None


def _resolver_carrito_servicio(cliente_id: str) -> Optional[str]:
    """Busca carrito de servicio activo para el cliente."""
    try:
        res = supabase.table("carrito_compras") \
            .select("id_carrito") \
            .eq("cliente_id", cliente_id) \
            .ilike("nombre", "%servicio%") \
            .limit(1) \
            .execute()
        if res.data:
            return res.data[0].get("id_carrito")
        return None
    except Exception:
        return None


def _subir_foto_servicio(carrito_id: str, archivo_foto: Any) -> Optional[str]:
    """
    Sube foto a Supabase Storage en bucket 'IMG', carpeta 'servicio'.
    
    Args:
        carrito_id: Para nombrar el archivo de forma Ãºnica
        archivo_foto: Archivo desde request.files
    
    Returns:
        URL pÃºblica de la foto o None si falla
    """
    try:
        print("[STORAGE] Iniciando upload de foto...")
        
        # Crear nombre Ãºnico: timestamp + carrito_id
        timestamp = int(time.time() * 1000)
        nombre_archivo = f"{carrito_id}_{timestamp}.jpg"
        ruta_storage = f"servicio/{nombre_archivo}"
        
        print(f"  Nombre archivo: {nombre_archivo}")
        print(f"  Ruta storage: {ruta_storage}")
        
        # Leer contenido del archivo
        contenido = archivo_foto.read()
        print(f"  TamaÃ±o archivo: {len(contenido)} bytes")
        
        # Subir a Supabase Storage bucket 'IMG'
        print("  Subiendo a bucket IMG...")
        response = supabase.storage.from_("IMG").upload(
            path=ruta_storage,
            file=contenido,
            file_options={"content-type": "image/jpeg"}
        )
        print(f"  Upload response: {response}")
        
        # Obtener URL pÃºblica
        print("  Obteniendo URL pÃºblica...")
        url_publica = supabase.storage.from_("IMG").get_public_url(ruta_storage)
        print(f"[SUCCESS] URL pÃºblica generada: {url_publica}")
        return url_publica
    
    except Exception as e:
        print(f"[ERROR] Error uploading foto: {e}")
        import traceback
        traceback.print_exc()
        return None


def _programar_limpieza_diferida(carrito_id: str, delay_seconds: int = 600) -> None:
    """Programa la eliminaciÃ³n de cortes y carrito despuÃ©s de un delay."""
    try:
        hilo = threading.Thread(
            target=_limpiar_carrito_y_cortes_despues_delay,
            args=(carrito_id, delay_seconds),
            daemon=True
        )
        hilo.start()
    except Exception as e:
        print(f"[WARN] No se pudo iniciar limpieza diferida para carrito {carrito_id}: {e}")


def _limpiar_carrito_y_cortes_despues_delay(carrito_id: str, delay_seconds: int) -> None:
    """Espera el tiempo indicado y luego elimina cortes y carrito del servicio."""
    try:
        print(f"[LIMPIEZA DIFERIDA] Esperando {delay_seconds}s para carrito {carrito_id}")
        time.sleep(delay_seconds)

        print(f"[LIMPIEZA DIFERIDA] Iniciando limpieza de carrito {carrito_id}")

        # Eliminar cortes asociados
        try:
            cortes_result = supabase.table("cortes").select("id_corte").eq("carrito_id", carrito_id).execute()
            cortes = cortes_result.data or []
            if cortes:
                for corte in cortes:
                    supabase.table("cortes").delete().eq("id_corte", corte.get("id_corte")).execute()
                print(f"[LIMPIEZA DIFERIDA] Cortes eliminados: {len(cortes)}")
            else:
                print("[LIMPIEZA DIFERIDA] Sin cortes para eliminar")
        except Exception as e:
            print(f"[WARN] [LIMPIEZA DIFERIDA] Error eliminando cortes: {e}")

        # Eliminar carrito
        try:
            supabase.table("carrito_compras").delete().eq("id_carrito", carrito_id).execute()
            print(f"[LIMPIEZA DIFERIDA] Carrito eliminado: {carrito_id}")
        except Exception as e:
            print(f"[WARN] [LIMPIEZA DIFERIDA] Error eliminando carrito: {e}")

    except Exception as e:
        print(f"[WARN] [LIMPIEZA DIFERIDA] Error general para carrito {carrito_id}: {e}")

