import base64
import re
from datetime import date
from typing import Any, Dict, Optional

from services.facturacion_service import FacturacionService
from services.supabase_client import supabase


class RegistroPagoComprobanteService:
    BUCKET_NAME = "COMPROBANTE"

    @staticmethod
    def guardar_comprobante(
        payload: Dict[str, Any],
        tipo_comprobante: str,
        monto: float,
        cliente_id: str,
        registro_pago_id: Optional[str] = None,
        metodo_pago_id: Optional[str] = None,
        serie: Optional[str] = None,
        correlativo: Optional[str] = None
    ) -> Dict[str, Any]:
        try:
            if not payload:
                return {"success": False, "message": "Payload requerido"}

            tipo_normalizado = (tipo_comprobante or "").strip().lower()
            if tipo_normalizado not in ("boleta", "factura"):
                return {
                    "success": False,
                    "message": "tipo_comprobante debe ser boleta o factura"
                }

            pdf_result = FacturacionService.generar_pdf(payload)
            if not pdf_result.get("success"):
                return {
                    "success": False,
                    "message": pdf_result.get("error") or "No se pudo generar PDF"
                }

            pdf_base64 = pdf_result.get("pdf")
            if not pdf_base64:
                return {"success": False, "message": "PDF vacio"}

            pdf_bytes = RegistroPagoComprobanteService._decode_pdf(pdf_base64)
            if not pdf_bytes:
                return {"success": False, "message": "PDF invalido"}

            carpeta = "BOLETAS" if tipo_normalizado == "boleta" else "FACTURAS"
            nombre_archivo = RegistroPagoComprobanteService._build_filename(
                tipo_comprobante=tipo_normalizado,
                serie=serie,
                correlativo=correlativo
            )
            ruta_storage = f"{carpeta}/{nombre_archivo}"

            supabase.storage.from_(RegistroPagoComprobanteService.BUCKET_NAME).upload(
                path=ruta_storage,
                file=pdf_bytes,
                file_options={"content-type": "application/pdf"}
            )

            documento_url = supabase.storage.from_(
                RegistroPagoComprobanteService.BUCKET_NAME
            ).get_public_url(ruta_storage)
            documento_url = RegistroPagoComprobanteService._extract_public_url(documento_url)

            if not documento_url:
                return {
                    "success": False,
                    "message": "No se pudo obtener URL publica del comprobante"
                }

            hoy = date.today().isoformat()
            total = round(float(monto or 0), 2)

            registro_objetivo_id = str(registro_pago_id or "").strip() or None

            if not registro_objetivo_id:
                try:
                    # Reusar el registro de pago más reciente ya enlazado a ventas del cliente,
                    # útil cuando el frontend no envía registro_pago_id.
                    ventas_con_registro = (
                        supabase.table("venta")
                        .select("registro_pago_id,fecha_venta")
                        .eq("cliente_id", cliente_id)
                        .not_.is_("registro_pago_id", "null")
                        .order("fecha_venta", desc=True)
                        .limit(1)
                        .execute()
                    )
                    fila = (ventas_con_registro.data or [None])[0]
                    if fila and fila.get("registro_pago_id"):
                        registro_objetivo_id = str(fila.get("registro_pago_id"))
                except Exception as exc_resolver:
                    print(f"[registro_pago] WARN no se pudo resolver registro por ventas: {exc_resolver}")

            if registro_objetivo_id:
                actualizado = (
                    supabase.table("registro_pago")
                    .update({
                        "fecha": hoy,
                        "total": total,
                        "documento": documento_url,
                    })
                    .eq("id_registro", registro_objetivo_id)
                    .execute()
                )
                registro = (actualizado.data or [None])[0]
                if registro:
                    return {
                        "success": True,
                        "message": "Comprobante vinculado al registro de pago",
                        "pdf": pdf_base64,
                        "documento_url": documento_url,
                        "storage_path": ruta_storage,
                        "registro_pago": registro
                    }

            registro_insert = supabase.table("registro_pago").insert({
                "fecha": hoy,
                "total": total,
                "documento": documento_url,
            }).execute()
            registro = (registro_insert.data or [None])[0]

            if not registro:
                return {
                    "success": False,
                    "message": "PDF guardado pero no se pudo registrar en tabla registro_pago"
                }

            registro_objetivo_id = registro.get("id_registro")

            # Enlazar ventas pendientes del cliente (sin registro_pago_id) al nuevo registro.
            try:
                ventas_pendientes = (
                    supabase.table("venta")
                    .select("id_venta,carrito_id,fecha_venta")
                    .eq("cliente_id", cliente_id)
                    .is_("registro_pago_id", "null")
                    .order("fecha_venta", desc=True)
                    .limit(300)
                    .execute()
                )
                filas = ventas_pendientes.data or []
                if filas:
                    carrito_ref = filas[0].get("carrito_id")
                    if carrito_ref:
                        ids = [f.get("id_venta") for f in filas if f.get("id_venta") and f.get("carrito_id") == carrito_ref]
                    else:
                        ids = [f.get("id_venta") for f in filas if f.get("id_venta")]
                    if ids:
                        (
                            supabase.table("venta")
                            .update({"registro_pago_id": registro_objetivo_id})
                            .in_("id_venta", ids)
                            .execute()
                        )
            except Exception as exc_link:
                print(f"[registro_pago] WARN no se pudo enlazar ventas pendientes: {exc_link}")

            return {
                "success": True,
                "message": "Comprobante guardado en storage y registrado en registro_pago",
                "pdf": pdf_base64,
                "documento_url": documento_url,
                "storage_path": ruta_storage,
                "registro_pago": registro
            }

        except Exception as e:
            return {"success": False, "message": str(e)}

    @staticmethod
    def _decode_pdf(pdf_base64: str) -> Optional[bytes]:
        try:
            if "," in pdf_base64 and "base64" in pdf_base64[:40]:
                pdf_base64 = pdf_base64.split(",", 1)[1]
            return base64.b64decode(pdf_base64)
        except Exception:
            return None

    @staticmethod
    def _build_filename(
        tipo_comprobante: str,
        serie: Optional[str],
        correlativo: Optional[str]
    ) -> str:
        safe_serie = RegistroPagoComprobanteService._safe_text(serie) or "SIN_SERIE"
        safe_corr = RegistroPagoComprobanteService._safe_text(correlativo) or "SIN_CORRELATIVO"
        prefijo = "BOLETA" if tipo_comprobante == "boleta" else "FACTURA"
        return f"{prefijo}_{safe_serie}-{safe_corr}.pdf"

    @staticmethod
    def _safe_text(value: Optional[str]) -> str:
        if not value:
            return ""
        return re.sub(r"[^A-Za-z0-9_-]", "", str(value)).strip()

    @staticmethod
    def _extract_public_url(url_obj: Any) -> Optional[str]:
        if isinstance(url_obj, str):
            return url_obj
        if isinstance(url_obj, dict):
            return (
                url_obj.get("publicUrl")
                or url_obj.get("publicURL")
                or url_obj.get("public_url")
                or url_obj.get("signedURL")
            )
        return getattr(url_obj, "publicUrl", None) or getattr(url_obj, "publicURL", None)
