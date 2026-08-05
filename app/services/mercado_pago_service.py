# -*- coding: utf-8 -*-
"""
Servicio de integracion con Mercado Pago
"""

import mercadopago
import os
import uuid
import re
from typing import Optional, Dict, List, Any
from dotenv import load_dotenv
from mercadopago import config

load_dotenv()

_SENSITIVE_KEYS = {
    "token", "card", "cvv", "security_code", "securitycode", "cardnumber",
    "card_number", "password", "access_token", "authorization",
}


def _sanitize_for_log(value, _depth=0):
    """Redacta campos sensibles antes de loggear una respuesta de Mercado Pago."""
    if _depth > 6:
        return "..."
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if str(k).lower() in _SENSITIVE_KEYS:
                out[k] = "***"
            elif str(k).lower() == "email":
                out[k] = re.sub(r"^(.).*(@.*)$", r"\1***\2", str(v)) if v else v
            elif str(k).lower() in ("number", "identification_number") and v:
                s = str(v)
                out[k] = f"***{s[-3:]}" if len(s) > 3 else "***"
            else:
                out[k] = _sanitize_for_log(v, _depth + 1)
        return out
    if isinstance(value, list):
        return [_sanitize_for_log(v, _depth + 1) for v in value]
    return value


class MercadoPagoService:

    def __init__(self):
        access_token = os.getenv("MERCADO_PAGO_ACCESS_TOKEN")
        if not access_token:
            raise ValueError("MERCADO_PAGO_ACCESS_TOKEN no configurado en .env")

        self.credential_env = "production" if access_token.startswith("APP_USR-") else "sandbox"
        print(f"[MP_SERVICE] SDK inicializado | ambiente={self.credential_env}", flush=True)
        self.sdk = mercadopago.SDK(access_token)

    # --------------------------------------------------
    # VALIDAR EMAIL (COMENTADO - ACEPTA CUALQUIER EMAIL)
    # --------------------------------------------------
    def _validar_email_test(self, email: str):
        # [OK] Ahora acepta cualquier email valido
        # Mercado Pago automaticamente lo convierte a test user en modo TEST
        if not email:
            raise ValueError("Email de comprador es obligatorio")

    # --------------------------------------------------
    # CREAR PREFERENCIA (CHECKOUT)
    # --------------------------------------------------
    def crear_preferencia_pago(
        self,
        carrito_id: str,
        cliente_id: str,
        items: List[Dict[str, Any]],
        email_cliente: str,
        total: float
    ) -> Dict[str, Any]:

        try:
            self._validar_email_test(email_cliente)

            preference_data = {
                "items": items,
                "payer": {
                    "email": email_cliente
                },
                "binary_mode": True,
                "statement_descriptor": "VIDRIOBRAS",
                "external_reference": carrito_id
            }

            print("[MP_SERVICE] Creando preferencia...")
            result = self.sdk.preference().create(preference_data)

            if result.get("status") == 201:
                response = result["response"]
                print(f"[MP_SERVICE] Preferencia creada {response.get('id')}")
                return {
                    "success": True,
                    "preference_id": response.get("id"),
                    "init_point": response.get("init_point"),
                    "sandbox_init_point": response.get("sandbox_init_point")
                }

            return {
                "success": False,
                "status": result.get("status"),
                "error": result.get("response", {}).get("message"),
                "cause": result.get("response", {}).get("cause")
            }

        except Exception as e:
            print(f"[MP_SERVICE] [ERROR] Error preferencia: {e}")
            return {"success": False, "error": str(e)}

    # --------------------------------------------------
    # PROCESAR PAGO CON YAPE
    # --------------------------------------------------
    def procesar_pago_yape(
        self,
        token: str,
        carrito_id: str,
        cliente_id: str,
        amount: float,
        payer_email: str,
        payer_identification: Dict[str, str],
        yape_phone: Optional[str] = None,
        yape_otp: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Procesa pagos con YAPE (billetera digital).
        YAPE es un payment_method_id de Mercado Pago que requiere
        manejo especial. No es una tarjeta de credito tradicional.
        """
        try:
            print(f"[MP_SERVICE] [YAPE] Iniciando procesamiento de YAPE")
            print(f"[MP_SERVICE]   Email: {payer_email}")
            print(f"[MP_SERVICE]   Monto: {amount}")
            print(f"[MP_SERVICE]   Carrito: {carrito_id}")
            print(f"[MP_SERVICE]   Token presente: {bool(token)}")
            print(f"[MP_SERVICE]   Telefono: {yape_phone if yape_phone else 'No proporcionado'}")

            # YAPE requiere solamente el payment_method_id
            # El token del SDK de Mercado Pago se aniade solo si esta disponible
            payer_data = {
                "email": payer_email
            }

            payer_identification_number = payer_identification.get("number") if payer_identification else None
            payer_identification_type = payer_identification.get("type") if payer_identification else None
            if payer_identification_number and payer_identification_number != "00000000":
                payer_data["identification"] = {
                    "type": payer_identification_type or "DNI",
                    "number": payer_identification_number
                }

            if yape_phone:
                payer_data["phone"] = {
                    "area_code": "51",
                    "number": yape_phone
                }

            payment_data = {
                "transaction_amount": float(amount),
                "description": f"Pedido VIDRIOBRAS - Carrito {carrito_id}",
                "payment_method_id": "yape",
                "binary_mode": True,
                "payer": payer_data,
                "external_reference": carrito_id,
                "metadata": {
                    "carrito_id": carrito_id,
                    "cliente_id": cliente_id
                }
            }

            if token:
                payment_data["token"] = token
                print(f"[MP_SERVICE]   Incluyendo token YAPE en el pedido")
            else:
                print(f"[MP_SERVICE]   No se detecto token YAPE, se enviara solo datos de payer")
            
            print(f"[MP_SERVICE] [YAPE] Payment Data COMPLETO a enviar: {payment_data}", flush=True)

            # ALTERNATIVA: Si YAPE requiere OTP directo (sin token)
            # Descomentar si es necesario:
            # if yape_otp:
            #     payment_data["additional_info"] = {
            #         "otp": yape_otp,
            #         "phone": yape_phone
            #     }

            request_options = config.RequestOptions()
            request_options.custom_headers = {
                "x-idempotency-key": str(uuid.uuid4())
            }

            print(f"[MP_SERVICE] >> Enviando a API Mercado Pago (YAPE)...")
            print(f"[MP_SERVICE] >> Payment Data: {dict(list(payment_data.items())[:5])}...")
            result = self.sdk.payment().create(payment_data, request_options)
            print(f"[MP_SERVICE] >> Respuesta MP completa: {result}", flush=True)
            print(f"[MP_SERVICE] >> Respuesta MP: status={result.get('status')}")

            if result.get("status") == 201:
                response = result["response"]
                print(f"[MP_SERVICE] [OK] Pago YAPE exitoso: ID={response.get('id')}, Status={response.get('status')}")
                return {
                    "success": True,
                    "payment_id": response.get("id"),
                    "status": response.get("status"),
                    "status_detail": response.get("status_detail"),
                    "amount": response.get("transaction_amount")
                }

            # Pago rechazado o pendiente por Mercado Pago
            response_data = result.get("response", {})
            error_msg = response_data.get("message", "Pago YAPE rechazado sin mensaje especifico")
            error_causes = response_data.get("cause", [])
            status_http = result.get("status")
            
            print(f"[MP_SERVICE] [!] Respuesta de Mercado Pago para YAPE")
            print(f"[MP_SERVICE]    Status HTTP: {status_http}")
            print(f"[MP_SERVICE]    Error: {error_msg}")
            print(f"[MP_SERVICE]    Causas COMPLETAS: {error_causes}", flush=True)
            print(f"[MP_SERVICE]    Response completa: {response_data}", flush=True)

            if status_http == 400 and token and "token" in (error_msg or "").lower():
                print("[MP_SERVICE] [YAPE] Error con token invalido, reintentando sin token...")
                payment_data.pop("token", None)
                retry_result = self.sdk.payment().create(payment_data, request_options)
                print(f"[MP_SERVICE] [YAPE] Reintento status={retry_result.get('status')}")
                if retry_result.get("status") == 201:
                    retry_response = retry_result["response"]
                    return {
                        "success": True,
                        "payment_id": retry_response.get("id"),
                        "status": retry_response.get("status"),
                        "status_detail": retry_response.get("status_detail"),
                        "amount": retry_response.get("transaction_amount")
                    }
                response_data = retry_result.get("response", {})
                error_msg = response_data.get("message", error_msg)
                error_causes = response_data.get("cause", error_causes)
                status_http = retry_result.get("status")

            if status_http == 403:
                return {
                    "success": False,
                    "message": "Pago Yape no autorizado por Mercado Pago (UNAUTHORIZED). Verifica credenciales y modo correcto.",
                    "status": 403,
                    "error": error_msg,
                    "cause": error_causes
                }

            # Determinacion si es rechazo o pendiente
            if status_http == 400:
                return {
                    "success": False,
                    "message": error_msg or "Datos de pago invalidos",
                    "status": status_http,
                    "error": error_msg,
                    "cause": error_causes
                }
            
            return {
                "success": False,
                "message": error_msg or "Pago YAPE no procesado",
                "status": status_http,
                "error": error_msg,
                "cause": error_causes
            }

        except Exception as e:
            print(f"[MP_SERVICE] [ERROR] Excepcion en procesamiento de YAPE")
            print(f"[MP_SERVICE]    {type(e).__name__}: {str(e)}")
            import traceback
            traceback.print_exc()
            return {
                "success": False,
                "message": f"Error procesando YAPE: {str(e)}",
                "error": str(e)
            }

    # --------------------------------------------------
    # PROCESAR PAGO CON TOKEN DE TARJETA
    # --------------------------------------------------
    def procesar_pago_con_token(
        self,
        token: str,
        carrito_id: str,
        cliente_id: str,
        amount: float,
        payment_method_id: str,
        issuer_id: Optional[str],
        installments: int,
        payer_email: str,
        payer_identification: Dict[str, str]
    ) -> Dict[str, Any]:

        idem_key = str(uuid.uuid4())
        try:
            # [OK] Email acepta cualquier formato (igual que mp_test que funciona)
            print(
                f"[MP_SERVICE][{idem_key}] [CARD] REQUEST recibido | "
                f"ambiente={self.credential_env} carrito={carrito_id} cliente={cliente_id} "
                f"monto={amount} payment_method_id={payment_method_id} issuer_id={issuer_id} "
                f"installments={installments} email={_sanitize_for_log({'email': payer_email})['email']} "
                f"token_presente={bool(token)} token_len={len(token) if token else 0}",
                flush=True,
            )

            payer_data = {
                "email": payer_email
            }

            payer_identification_number = payer_identification.get("number") if payer_identification else None
            payer_identification_type = payer_identification.get("type") if payer_identification else None
            if payer_identification_number and payer_identification_number != "00000000":
                payer_data["identification"] = {
                    "type": payer_identification_type or "DNI",
                    "number": payer_identification_number
                }

            payment_data = {
                "transaction_amount": float(amount),
                "token": token,
                "description": f"Pedido VIDRIOBRAS - Carrito {carrito_id}",
                "installments": int(installments),
                "payment_method_id": payment_method_id,
                "binary_mode": True,
                "payer": payer_data,
                "external_reference": carrito_id,
                "metadata": {
                    "carrito_id": carrito_id,
                    "cliente_id": cliente_id
                }
            }

            # [CLEAN] issuer_id solo si existe
            if issuer_id:
                payment_data["issuer_id"] = issuer_id

            request_options = config.RequestOptions()
            request_options.custom_headers = {
                "x-idempotency-key": idem_key
            }

            print(
                f"[MP_SERVICE][{idem_key}] >> Enviando a proveedor=mercadopago "
                f"endpoint=POST /v1/payments ambiente={self.credential_env} "
                f"payload={_sanitize_for_log(payment_data)}",
                flush=True,
            )
            result = self.sdk.payment().create(payment_data, request_options)
            print(f"[MP_SERVICE][{idem_key}] << HTTP status del proveedor={result.get('status')}", flush=True)

            if result.get("status") == 201:
                response = result["response"]
                print(
                    f"[MP_SERVICE][{idem_key}] [OK] Pago aprobado | "
                    f"response={_sanitize_for_log(response)}",
                    flush=True,
                )
                return {
                    "success": True,
                    "payment_id": response.get("id"),
                    "status": response.get("status"),
                    "status_detail": response.get("status_detail"),
                    "amount": response.get("transaction_amount")
                }

            # Pago rechazado por Mercado Pago
            response_data = result.get("response", {})
            error_msg = response_data.get("message", "Rechazado sin mensaje")
            error_causes = response_data.get("cause", [])
            error_code = response_data.get("code")
            blocked_by = response_data.get("blocked_by")

            print(
                f"[MP_SERVICE][{idem_key}] [ERROR] Pago rechazado | "
                f"status_http={result.get('status')} code={error_code} blocked_by={blocked_by} "
                f"mensaje={error_msg} causas={error_causes} "
                f"response_completo={_sanitize_for_log(response_data)}",
                flush=True,
            )

            if result.get("status") == 403:
                return {
                    "success": False,
                    "message": "Pago no autorizado por Mercado Pago (UNAUTHORIZED). Revisa las credenciales, el modo Sandbox/Production y configura la cuenta correctamente.",
                    "status": 403,
                    "error": error_msg,
                    "cause": error_causes
                }

            # Manejo especifico para not_result_by_params (codigo 10102)
            if result.get("status") == 400 and (
                (error_msg or "").lower().strip() == "not_result_by_params" or
                any([c.get("code") == 10102 for c in error_causes if isinstance(c, dict)])
            ):
                print(f"[MP_SERVICE][{idem_key}] [CARD] not_result_by_params detectado, reintentando sin issuer_id ni binary_mode", flush=True)
                fallback_data = payment_data.copy()
                fallback_data.pop("issuer_id", None)
                fallback_data.pop("binary_mode", None)

                retry_result = self.sdk.payment().create(fallback_data, request_options)
                print(f"[MP_SERVICE][{idem_key}] [CARD] Reintento fallback status={retry_result.get('status')}", flush=True)
                if retry_result.get("status") == 201:
                    retry_response = retry_result["response"]
                    print(f"[MP_SERVICE][{idem_key}] [OK] Pago aprobado tras reintento fallback: ID={retry_response.get('id')}", flush=True)
                    return {
                        "success": True,
                        "payment_id": retry_response.get("id"),
                        "status": retry_response.get("status"),
                        "status_detail": retry_response.get("status_detail"),
                        "amount": retry_response.get("transaction_amount")
                    }

                fallback_response = retry_result.get("response", {})
                print(f"[MP_SERVICE][{idem_key}] [CARD] Reintento fallback result: {_sanitize_for_log(fallback_response)}", flush=True)
                return {
                    "success": False,
                    "message": fallback_response.get("message", error_msg),
                    "status": retry_result.get("status"),
                    "error": fallback_response.get("message", error_msg),
                    "cause": fallback_response.get("cause", error_causes)
                }

            return {
                "success": False,
                "message": error_msg,
                "status": result.get("status"),
                "error": error_msg,
                "cause": error_causes
            }

        except Exception as e:
            print(f"[MP_SERVICE][{idem_key}] [ERROR] Excepcion: {type(e).__name__}: {str(e)}", flush=True)
            import traceback
            traceback.print_exc()
            return {"success": False, "message": str(e), "error": str(e)}


# Instancia global
mercado_pago_service = MercadoPagoService()
