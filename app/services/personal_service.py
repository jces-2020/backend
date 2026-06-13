"""
Servicio para gestion de personal.
Consulta Supabase para obtener informacion del personal y sus bonos.
"""

from typing import Dict, List, Any, Optional

from services.supabase_client import supabase
from services.pago_balance_service import restar_monto_empresa


def get_all_personal() -> List[Dict[str, Any]]:
    """
    Obtiene todo el personal con informacion de tipo_personal.
    """
    try:
        result = supabase.table("personal").select(
            "*, tipo_personal:tipo_personal_id(id_tipo, descripcion)"
        ).execute()
        print(f"[personal_service] fetched {len(result.data or [])} personal records")
        return result.data or []
    except Exception as exc:  # noqa: BLE001
        print(f"[personal_service] error fetching personal: {exc}")
        import traceback
        traceback.print_exc()
        return []


def get_personal_by_id(personal_id: str) -> Optional[Dict[str, Any]]:
    """
    Obtiene detalles de un personal especifico.
    """
    try:
        result = supabase.table("personal").select(
            "*, tipo_personal:tipo_personal_id(id_tipo, descripcion)"
        ).eq("id_personal", personal_id).execute()
        if result.data:
            return result.data[0]
        return None
    except Exception as exc:  # noqa: BLE001
        print(f"[personal_service] error fetching personal by id: {exc}")
        import traceback
        traceback.print_exc()
        return None


def create_personal(
    nombre: str,
    codigo: str,
    tipo_personal_id: Optional[str] = None,
    cv: Optional[str] = None,
    fecha_nacimiento: Optional[str] = None,
    correo: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Crea un nuevo personal.
    """
    try:
        insert_data: Dict[str, Any] = {
            "nombre": nombre.strip(),
            "Codigo": codigo.strip(),
        }

        if tipo_personal_id:
            insert_data["tipo_personal_id"] = tipo_personal_id
        if cv:
            insert_data["cv"] = cv.strip()
        if fecha_nacimiento:
            insert_data["fecha_nacimiento"] = fecha_nacimiento
        if correo:
            insert_data["correo"] = correo.strip()

        result = supabase.table("personal").insert(insert_data).execute()
        if result.data:
            return result.data[0]
        return None
    except Exception as exc:  # noqa: BLE001
        print(f"[personal_service] error creating personal: {exc}")
        return None


def get_bonos_personal(personal_id: str) -> List[Dict[str, Any]]:
    """
    Obtiene los bonos asignados a un personal.
    """
    try:
        result = supabase.table("bonos_personal").select(
            "bono_id, bonos:bono_id(id_bono, descripcion)"
        ).eq("personal_id", personal_id).execute()
        return result.data or []
    except Exception as exc:  # noqa: BLE001
        print(f"[personal_service] error fetching bonos: {exc}")
        return []


def get_all_bonos() -> List[Dict[str, Any]]:
    """
    Obtiene todos los bonos disponibles.
    """
    try:
        result = supabase.table("bonos").select("id_bono, descripcion").execute()
        return result.data or []
    except Exception as exc:  # noqa: BLE001
        print(f"[personal_service] error fetching all bonos: {exc}")
        return []


def create_bono(descripcion: str) -> Optional[Dict[str, Any]]:
    """
    Crea un nuevo bono en la tabla bonos.
    """
    try:
        descripcion_clean = descripcion.strip()
        if not descripcion_clean:
            return None

        result = supabase.table("bonos").insert({
            "descripcion": descripcion_clean,
        }).execute()
        if result.data:
            return result.data[0]
        return None
    except Exception as exc:  # noqa: BLE001
        print(f"[personal_service] error creating bono: {exc}")
        return None


def delete_bono(bono_id: str) -> bool:
    """
    Elimina un bono del catalogo y sus asignaciones relacionadas.
    """
    try:
        supabase.table("bonos_personal").delete().eq("bono_id", bono_id).execute()
        supabase.table("bonos").delete().eq("id_bono", bono_id).execute()
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"[personal_service] error deleting bono: {exc}")
        return False


def add_bono_to_personal(personal_id: str, bono_id: str) -> bool:
    """
    Asigna un bono a un personal.
    """
    try:
        insert_data = {
            "personal_id": personal_id,
            "bono_id": bono_id
        }

        try:
            result = supabase.table("bonos_personal").insert(insert_data).execute()
            return bool(result.data)
        except Exception as exc_insert:  # noqa: BLE001
            error_str = str(exc_insert)

            # Si ya existe la relacion bono-personal, lo tratamos como operacion idempotente.
            if "23505" in error_str or "duplicate key value" in error_str:
                return True

            raise
    except Exception as exc:  # noqa: BLE001
        print(f"[personal_service] error adding bono: {exc}")
        return False


def remove_bono_from_personal(personal_id: str, bono_id: str) -> bool:
    """
    Elimina un bono de un personal.
    """
    try:
        result = supabase.table("bonos_personal").delete().eq(
            "personal_id", personal_id
        ).eq("bono_id", bono_id).execute()
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"[personal_service] error removing bono: {exc}")
        return False


def create_pago(personal_id: str, monto: float, fecha: str) -> Optional[Dict[str, Any]]:
    """
    Registra pago de personal restando al saldo acumulado de empresa en tabla pago.
    Mantiene la tabla pago como saldo unico actualizado.
    """
    try:
        _ = personal_id  # Conservado por compatibilidad de firma.
        _ = fecha
        return restar_monto_empresa(float(monto))
    except Exception as exc:  # noqa: BLE001
        print(f"[personal_service] error creating pago: {exc}")
        return None


def create_gasto_personal_bono(
    monto: float,
    fecha: str,
    caja_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Crea un gasto por pago de bono al personal.
    Registra el tipo fijo como 'personal bono' en la tabla gastos.
    """
    try:
        insert_data: Dict[str, Any] = {
            "monto": monto,
            "fecha": fecha,
            "tipo": "personal bono",
        }
        if caja_id:
            insert_data["caja_id"] = caja_id

        result = supabase.table("gastos").insert(insert_data).execute()
        if result.data:
            return result.data[0]
        return None
    except Exception as exc:  # noqa: BLE001
        print(f"[personal_service] error creating gasto personal bono: {exc}")
        return None


def create_gasto_personal(
    monto: float,
    fecha: str,
    caja_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Crea un gasto por pago mensual al personal.
    Registra el tipo fijo como 'personal' en la tabla gastos.
    """
    try:
        insert_data: Dict[str, Any] = {
            "monto": monto,
            "fecha": fecha,
            "tipo": "personal",
        }
        if caja_id:
            insert_data["caja_id"] = caja_id

        result = supabase.table("gastos").insert(insert_data).execute()
        if result.data:
            return result.data[0]
        return None
    except Exception as exc:  # noqa: BLE001
        print(f"[personal_service] error creating gasto personal: {exc}")
        return None


def upload_cv_pdf(file_content: bytes, filename: str) -> Optional[str]:
    """
    Sube un archivo PDF a Supabase Storage en la carpeta CV/PERSONAL.
    Retorna la URL publica del archivo si es exitoso, None si falla.
    """
    try:
        # Generar nombre unico para el archivo usando timestamp
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_filename = f"{timestamp}_{filename}"
        
        # Subir a Storage en la carpeta PERSONAL dentro del bucket CV
        path = f"PERSONAL/{unique_filename}"
        result = supabase.storage.from_("CV").upload(path, file_content, file_options={"content-type": "application/pdf"})
        
        # Obtener URL publica del archivo
        url_obj = supabase.storage.from_("CV").get_public_url(path)
        
        # Extraer la URL de acuerdo al tipo de respuesta
        if isinstance(url_obj, str):
            url = url_obj
        elif isinstance(url_obj, dict):
            url = (
                url_obj.get("publicUrl")
                or url_obj.get("publicURL")
                or url_obj.get("public_url")
            )
        else:
            url = getattr(url_obj, "publicUrl", None) or getattr(url_obj, "publicURL", None)
        
        if not url:
            print(f"[personal_service] Could not extract URL from: {url_obj}")
            return None
        
        print(f"[personal_service] CV uploaded successfully: {path} -> {url}")
        return url
    except Exception as exc:  # noqa: BLE001
        print(f"[personal_service] error uploading CV PDF: {exc}")
        import traceback
        traceback.print_exc()
        return None


def delete_personal(personal_id: str) -> bool:
    """Elimina un registro de personal por su ID."""
    try:
        supabase.table("personal").delete().eq("id_personal", personal_id).execute()
        print(f"[personal_service] deleted personal {personal_id}")
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"[personal_service] error deleting personal {personal_id}: {exc}")
        return False


__all__ = [
    "get_all_personal",
    "get_personal_by_id",
    "create_personal",
    "delete_personal",
    "get_bonos_personal",
    "get_all_bonos",
    "create_bono",
    "delete_bono",
    "add_bono_to_personal",
    "remove_bono_from_personal",
    "create_pago",
    "create_gasto_personal_bono",
    "create_gasto_personal",
    "upload_cv_pdf",
]
