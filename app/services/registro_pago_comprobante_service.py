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

            insert_data = {
                "fecha": date.today().isoformat(),
                "monto": monto,
                "documento": documento_url,
                "cliente_id": cliente_id,
                "metodo_pago_id": metodo_pago_id
            }

            # Si llega un id de registro_pago, actualizar ese registro exacto.
            if registro_pago_id:
                try:
                    existente_por_id = supabase.table("registro_pago").select(
                        "id_registro, cliente_id"
                    ).eq("id_registro", registro_pago_id).limit(1).execute()

                    fila = (existente_por_id.data or [None])[0]
                    if fila and str(fila.get("cliente_id") or "") == str(cliente_id):
                        update_payload = {
                            "documento": documento_url,
                            "metodo_pago_id": metodo_pago_id,
                        }
                        actualizado = supabase.table("registro_pago").update(
                            update_payload
                        ).eq("id_registro", registro_pago_id).execute()
                        registro_actualizado = (actualizado.data or [None])[0] or {"id_registro": registro_pago_id}
                        return {
                            "success": True,
                            "message": "Comprobante vinculado al registro de pago por id",
                            "pdf": pdf_base64,
                            "documento_url": documento_url,
                            "storage_path": ruta_storage,
                            "registro_pago": registro_actualizado
                        }
                except Exception as exc_id:
                    print(f"[registro_pago] Error actualizando por id: {exc_id}")

            # Si ya existe un registro de pago pendiente (sin documento) para hoy,
            # actualizarlo en lugar de insertar uno nuevo.
            try:
                pendientes_null = supabase.table("registro_pago").select(
                    "id_registro, monto"
                ).eq("cliente_id", cliente_id).eq(
                    "fecha", insert_data["fecha"]
                ).is_("documento", "null").order("id_registro", desc=True).limit(50).execute()

                pendientes_empty = supabase.table("registro_pago").select(
                    "id_registro, monto"
                ).eq("cliente_id", cliente_id).eq(
                    "fecha", insert_data["fecha"]
                ).eq("documento", "").order("id_registro", desc=True).limit(50).execute()

                pendientes = (pendientes_null.data or []) + (pendientes_empty.data or [])

                id_registro = None
                if pendientes:
                    monto_objetivo = round(float(monto or 0), 2)

                    # 1) match exacto a 2 decimales
                    exactos = [
                        p for p in pendientes
                        if round(float(p.get("monto") or 0), 2) == monto_objetivo
                    ]
                    if exactos:
                        id_registro = exactos[0].get("id_registro")
                    else:
                        # 2) fallback por cercania para cubrir redondeos/IGV
                        ordenados = sorted(
                            pendientes,
                            key=lambda p: abs(float(p.get("monto") or 0) - float(monto or 0))
                        )
                        candidato = ordenados[0] if ordenados else None
                        if candidato:
                            diferencia = abs(float(candidato.get("monto") or 0) - float(monto or 0))
                            if diferencia <= 0.30:
                                id_registro = candidato.get("id_registro")

                if id_registro:
                    update_payload = {
                        "documento": documento_url,
                        "metodo_pago_id": metodo_pago_id,
                    }
                    actualizado = supabase.table("registro_pago").update(
                        update_payload
                    ).eq("id_registro", id_registro).execute()

                    registro_actualizado = (actualizado.data or [None])[0] or {"id_registro": id_registro}
                    return {
                        "success": True,
                        "message": "Comprobante vinculado al registro de pago existente",
                        "pdf": pdf_base64,
                        "documento_url": documento_url,
                        "storage_path": ruta_storage,
                        "registro_pago": registro_actualizado
                    }
            except Exception as exc_pending:
                print(f"[registro_pago] Error actualizando pendiente: {exc_pending}")

            # Validar que no sea duplicado: mismo cliente, mismo monto, mismo día
            try:
                existing = supabase.table("registro_pago").select(
                    "id_registro"
                ).eq("cliente_id", cliente_id).eq("monto", monto).eq(
                    "fecha", insert_data["fecha"]
                ).eq("documento", documento_url).execute()
                
                if existing.data and len(existing.data) > 0:
                    print(f"[registro_pago] Duplicado detectado para cliente {cliente_id}, monto {monto}")
                    return {
                        "success": True,
                        "message": "Comprobante ya registrado",
                        "pdf": pdf_base64,
                        "documento_url": documento_url,
                        "storage_path": ruta_storage,
                        "registro_pago": existing.data[0]
                    }
            except Exception as exc_dup:
                print(f"[registro_pago] Error validando duplicado: {exc_dup}")

            registro_insert = supabase.table("registro_pago").insert(insert_data).execute()
            registro = (registro_insert.data or [None])[0]

            if not registro:
                return {
                    "success": False,
                    "message": "PDF guardado pero no se pudo registrar en tabla registro_pago"
                }

            return {
                "success": True,
                "message": "Comprobante guardado en storage y registrado en pago",
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
