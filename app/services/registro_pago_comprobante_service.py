import base64
import re
import uuid
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

            bucket_name = str(RegistroPagoComprobanteService.BUCKET_NAME or "COMPROBANTE").upper().strip()
            carpeta = "BOLETAS" if tipo_normalizado == "boleta" else "FACTURAS"
            carpeta = carpeta.upper().strip()
            nombre_archivo = RegistroPagoComprobanteService._build_filename(
                tipo_comprobante=tipo_normalizado,
                serie=serie,
                correlativo=correlativo
            )
            ruta_storage = f"{carpeta}/{nombre_archivo}"

            try:
                supabase.storage.from_(bucket_name).upload(
                    path=ruta_storage,
                    file=pdf_bytes,
                    file_options={"content-type": "application/pdf", "upsert": "true"}
                )
            except Exception:
                # Fallback: si el provider rechaza upsert o hay colisión de nombre,
                # subir con nombre único para no perder el comprobante.
                ruta_storage = f"{carpeta}/{RegistroPagoComprobanteService._build_filename(tipo_normalizado, serie, correlativo, force_unique=True)}"
                supabase.storage.from_(bucket_name).upload(
                    path=ruta_storage,
                    file=pdf_bytes,
                    file_options={"content-type": "application/pdf"}
                )

            documento_url = supabase.storage.from_(
                bucket_name
            ).get_public_url(ruta_storage)
            documento_url = RegistroPagoComprobanteService._extract_public_url(documento_url)

            if not documento_url:
                return {
                    "success": False,
                    "message": "No se pudo obtener URL publica del comprobante"
                }

            hoy = date.today().isoformat()
            total = round(float(monto or 0), 2)

            ventas_recientes_cliente = []
            carrito_ref = None
            try:
                ventas_recientes = (
                    supabase.table("venta")
                    .select("id_venta,carrito_id,registro_pago_id,fecha_venta,monto")
                    .eq("cliente_id", cliente_id)
                    .order("fecha_venta", desc=True)
                    .limit(500)
                    .execute()
                )
                ventas_recientes_cliente = ventas_recientes.data or []
                # Elegir el carrito pendiente más reciente (sin registro_pago_id).
                for row in ventas_recientes_cliente:
                    if row.get("id_venta") and not row.get("registro_pago_id"):
                        carrito_ref = row.get("carrito_id")
                        break
            except Exception as exc_ventas:
                print(f"[registro_pago] WARN no se pudieron cargar ventas recientes: {exc_ventas}")

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
                filas = [
                    f for f in (ventas_recientes_cliente or [])
                    if f.get("id_venta")
                    and not f.get("registro_pago_id")
                    and (not carrito_ref or f.get("carrito_id") == carrito_ref)
                ]
                if filas:
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
                "message": "Comprobante creado en storage y registrado como nuevo en registro_pago",
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
        correlativo: Optional[str],
        force_unique: bool = False,
    ) -> str:
        safe_serie = RegistroPagoComprobanteService._safe_text(serie) or "SIN_SERIE"
        safe_corr = RegistroPagoComprobanteService._safe_text(correlativo) or "SIN_CORRELATIVO"
        prefijo = "BOLETA" if tipo_comprobante == "boleta" else "FACTURA"
        if force_unique:
            return f"{prefijo}_{safe_serie}-{safe_corr}-{uuid.uuid4().hex[:10]}.pdf"
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
