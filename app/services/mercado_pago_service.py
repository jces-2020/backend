# -*- coding: utf-8 -*-
"""
Servicio de integracion con Mercado Pago
"""

import mercadopago
import os
import uuid
import re
import requests
from typing import Optional, Dict, List, Any
from dotenv import load_dotenv
from mercadopago import config

load_dotenv()

_SENSITIVE_KEYS = {
    "token", "card", "cvv", "security_code", "securitycode", "cardnumber",
    "card_number", "password", "access_token", "authorization",
}


def _classify_mp_error(status_http, error_code, blocked_by, error_msg):
    """Clasifica el rechazo de Mercado Pago para diagnostico interno.

    Evidencia (código fuente oficial mercadopago/sdk-python 2.2.1,
    mercadopago/config/request_options.py::get_headers): Authorization,
    Content-Type y x-idempotency-key se arman correctamente siempre que el
    SDK tenga un access_token configurado -> un PA_UNAUTHORIZED_RESULT_FROM_POLICIES
    con blocked_by=PolicyAgent NO es un header faltante, es el motor de
    riesgo/cumplimiento de la cuenta rechazando la operación puntual.
    """
    code = (error_code or "").upper()
    msg = (error_msg or "").lower()

    if blocked_by == "PolicyAgent" or code.startswith("PA_"):
        return "CONFIGURATION_ERROR"
    if status_http in (401, 403):
        return "AUTHENTICATION_ERROR"
    if "token" in msg and any(w in msg for w in ("invalid", "used", "expired", "not found")):
        return "CARD_TOKEN_ERROR"
    if any(w in msg for w in ("payment_method", "issuer", "payment method")):
        return "PAYMENT_METHOD_ERROR"
    if status_http == 400:
        return "PAYMENT_REJECTED"
    return "PROVIDER_ERROR"


_REJECTED_MESSAGES = {
    "cc_rejected_insufficient_amount": "Fondos insuficientes en la tarjeta.",
    "cc_rejected_bad_filled_security_code": "Código de seguridad (CVV) incorrecto.",
    "cc_rejected_bad_filled_date": "Fecha de vencimiento incorrecta.",
    "cc_rejected_bad_filled_other": "Revisa los datos de la tarjeta.",
    "cc_rejected_bad_filled_card_number": "Número de tarjeta incorrecto.",
    "cc_rejected_call_for_authorize": "Debes autorizar el pago con tu banco.",
    "cc_rejected_card_disabled": "Tarjeta deshabilitada. Contacta a tu banco.",
    "cc_rejected_card_error": "No se pudo procesar la tarjeta.",
    "cc_rejected_duplicated_payment": "Ya existe un pago con estos mismos datos.",
    "cc_rejected_high_risk": "El pago fue rechazado por el sistema de prevención de fraude.",
    "cc_rejected_max_attempts": "Se alcanzó el límite de intentos con esta tarjeta.",
    "cc_rejected_other_reason": "El banco emisor rechazó el pago.",
}


def _mensaje_por_status_detail(status_detail):
    return _REJECTED_MESSAGES.get(status_detail, "El banco emisor rechazó el pago.")


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

    # MODO PRODUCCION: llama a la API real de Mercado Pago y cobra de verdad.
    MODO_PRUEBA = True

    def __init__(self):
        access_token = os.getenv("MERCADO_PAGO_ACCESS_TOKEN")
        if not access_token:
            raise ValueError("MERCADO_PAGO_ACCESS_TOKEN no configurado en .env")

        self.credential_env = "production" if access_token.startswith("APP_USR-") else "sandbox"
        print(f"[MP_SERVICE] SDK inicializado | ambiente={self.credential_env}", flush=True)
        self.access_token = access_token
        self.sdk = mercadopago.SDK(access_token)

        backend_url = os.getenv("BACKEND_PUBLIC_URL", "https://api.vidriobras.com").rstrip("/")
        self.notification_url = f"{backend_url}/api/pagos/webhook"

    # --------------------------------------------------
    # VALIDAR EMAIL (COMENTADO - ACEPTA CUALQUIER EMAIL)
    # --------------------------------------------------
    def _validar_email_test(self, email: str):
        # [OK] Ahora acepta cualquier email valido
        # Mercado Pago automaticamente lo convierte a test user en modo TEST
        if not email:
            raise ValueError("Email de comprador es obligatorio")

    def _result_from_payment_response(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """Clasifica la respuesta de un pago creado (HTTP 201) segun el campo `status`.

        MP responde 201 tanto para pagos aprobados como pendientes o rechazados;
        el estado real esta en `status`/`status_detail`, no en el codigo HTTP.
        """
        estado = response.get("status")
        base = {
            "payment_id": response.get("id"),
            "status": estado,
            "status_detail": response.get("status_detail"),
            "amount": response.get("transaction_amount"),
        }

        if estado == "approved":
            return {"success": True, **base}

        if estado in ("pending", "in_process", "authorized"):
            return {
                "success": False,
                "pending": True,
                "message": "Tu pago está siendo revisado por Mercado Pago. Te notificaremos cuando se confirme.",
                **base,
            }

        return {
            "success": False,
            "message": _mensaje_por_status_detail(response.get("status_detail")),
            "error_category": "PAYMENT_REJECTED",
            **base,
        }

    def _create_payment(self, payment_data: Dict[str, Any], request_options) -> Dict[str, Any]:
        """Crea un pago llamando directo a la API REST (no via SDK).

        El SDK python descarta los headers de la respuesta y con ellos el
        `X-Request-Id` que Mercado Pago pide para investigar rechazos como
        PA_UNAUTHORIZED_RESULT_FROM_POLICIES. Replica los mismos headers que
        arma el SDK (misma x-idempotency-key) para que sea el mismo intento
        de pago, no uno adicional.
        """
        if MercadoPagoService.MODO_PRUEBA:
            print("[MP_SERVICE] [MODO_PRUEBA] Pago simulado, NO se llama a Mercado Pago", flush=True)
            fake_id = f"SIMULADO-{uuid.uuid4().hex[:12]}"
            return {
                "status": 201,
                "response": {
                    "id": fake_id,
                    "status": "approved",
                    "status_detail": "accredited",
                    "transaction_amount": payment_data.get("transaction_amount"),
                },
                "request_id": fake_id,
            }

        request_options.access_token = self.access_token
        headers = request_options.get_headers()
        headers["Content-Type"] = "application/json"
        try:
            resp = requests.post(
                "https://api.mercadopago.com/v1/payments",
                json=payment_data,
                headers=headers,
                timeout=request_options.connection_timeout or 60,
            )
            return {
                "status": resp.status_code,
                "response": resp.json(),
                "request_id": resp.headers.get("X-Request-Id") or resp.headers.get("x-request-id"),
            }
        except Exception as e:
            return {"status": 500, "response": {"message": str(e)}, "request_id": None}

    # --------------------------------------------------
    # CONSULTAR ESTADO DE UN PAGO (usado por el webhook)
    # --------------------------------------------------
    def obtener_pago(self, payment_id: str) -> Dict[str, Any]:
        try:
            result = self.sdk.payment().get(payment_id)
            if result.get("status") == 200:
                return {"success": True, **result["response"]}
            return {
                "success": False,
                "status": result.get("status"),
                "error": result.get("response"),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

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
                "statement_descriptor": "VIDRIOBRAS",
                "external_reference": carrito_id,
                "notification_url": self.notification_url
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
        installments: int = 1,
        yape_phone: Optional[str] = None,
        yape_otp: Optional[str] = None,
        payer_first_name: Optional[str] = None,
        payer_last_name: Optional[str] = None,
        items: Optional[List[Dict[str, Any]]] = None,
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

            if payer_first_name:
                payer_data["first_name"] = payer_first_name
            if payer_last_name:
                payer_data["last_name"] = payer_last_name

            payment_data = {
                "transaction_amount": float(amount),
                "description": f"Pedido VIDRIOBRAS - Carrito {carrito_id}",
                "statement_descriptor": "VIDRIOBRAS",
                "payment_method_id": "yape",
                "installments": int(installments) or 1,
                "payer": payer_data,
                "external_reference": carrito_id,
                "notification_url": self.notification_url,
                "metadata": {
                    "carrito_id": carrito_id,
                    "cliente_id": cliente_id
                }
            }

            if items:
                payment_data["additional_info"] = {"items": items}

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
            result = self._create_payment(payment_data, request_options)
            print(f"[MP_SERVICE] >> Respuesta MP completa: {result}", flush=True)
            print(f"[MP_SERVICE] >> Respuesta MP: status={result.get('status')} X-Request-Id={result.get('request_id')}")

            if result.get("status") == 201:
                response = result["response"]
                resultado = self._result_from_payment_response(response)
                print(f"[MP_SERVICE] [YAPE] Pago clasificado: status={resultado.get('status')} success={resultado.get('success')}", flush=True)
                return resultado

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
            print(f"[MP_SERVICE]    X-Request-Id: {result.get('request_id')}", flush=True)

            if status_http == 400 and token and "token" in (error_msg or "").lower():
                print("[MP_SERVICE] [YAPE] Error con token invalido, reintentando sin token...")
                payment_data.pop("token", None)
                retry_result = self._create_payment(payment_data, request_options)
                print(f"[MP_SERVICE] [YAPE] Reintento status={retry_result.get('status')}")
                if retry_result.get("status") == 201:
                    retry_response = retry_result["response"]
                    return self._result_from_payment_response(retry_response)
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
                    "request_id": result.get("request_id"),
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
        payer_identification: Dict[str, str],
        device_id: Optional[str] = None,
        payer_first_name: Optional[str] = None,
        payer_last_name: Optional[str] = None,
        items: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:

        idem_key = str(uuid.uuid4())
        try:
            # [OK] Email acepta cualquier formato (igual que mp_test que funciona)
            print(
                f"[MP_SERVICE][{idem_key}] [CARD] REQUEST recibido | "
                f"ambiente={self.credential_env} carrito={carrito_id} cliente={cliente_id} "
                f"monto={amount} payment_method_id={payment_method_id} issuer_id={issuer_id} "
                f"installments={installments} email={_sanitize_for_log({'email': payer_email})['email']} "
                f"token_presente={bool(token)} token_len={len(token) if token else 0} "
                f"device_id_presente={bool(device_id)}",
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

            if payer_first_name:
                payer_data["first_name"] = payer_first_name
            if payer_last_name:
                payer_data["last_name"] = payer_last_name

            payment_data = {
                "transaction_amount": float(amount),
                "token": token,
                "description": f"Pedido VIDRIOBRAS - Carrito {carrito_id}",
                "statement_descriptor": "VIDRIOBRAS",
                "installments": int(installments),
                "payment_method_id": payment_method_id,
                "payer": payer_data,
                "external_reference": carrito_id,
                "notification_url": self.notification_url,
                "metadata": {
                    "carrito_id": carrito_id,
                    "cliente_id": cliente_id
                }
            }

            # [CLEAN] issuer_id solo si existe
            if issuer_id:
                payment_data["issuer_id"] = issuer_id

            if items:
                payment_data["additional_info"] = {"items": items}

            request_options = config.RequestOptions()
            custom_headers = {"x-idempotency-key": idem_key}
            if device_id:
                custom_headers["X-meli-session-id"] = device_id
            request_options.custom_headers = custom_headers

            print(
                f"[MP_SERVICE][{idem_key}] >> Enviando a proveedor=mercadopago "
                f"endpoint=POST /v1/payments ambiente={self.credential_env} "
                f"X-meli-session-id_presente={bool(device_id)} "
                f"payload={_sanitize_for_log(payment_data)}",
                flush=True,
            )
            result = self._create_payment(payment_data, request_options)
            print(
                f"[MP_SERVICE][{idem_key}] << HTTP status del proveedor={result.get('status')} "
                f"X-Request-Id={result.get('request_id')}",
                flush=True,
            )

            if result.get("status") == 201:
                response = result["response"]
                resultado = self._result_from_payment_response(response)
                print(
                    f"[MP_SERVICE][{idem_key}] [CARD] Pago clasificado | "
                    f"status={resultado.get('status')} success={resultado.get('success')} "
                    f"response={_sanitize_for_log(response)}",
                    flush=True,
                )
                return resultado

            # Pago rechazado por Mercado Pago
            response_data = result.get("response", {})
            error_msg = response_data.get("message", "Rechazado sin mensaje")
            error_causes = response_data.get("cause", [])
            error_code = response_data.get("code")
            blocked_by = response_data.get("blocked_by")

            print(
                f"[MP_SERVICE][{idem_key}] [ERROR] Pago rechazado | "
                f"status_http={result.get('status')} code={error_code} blocked_by={blocked_by} "
                f"mensaje={error_msg} causas={error_causes} X-Request-Id={result.get('request_id')} "
                f"response_completo={_sanitize_for_log(response_data)}",
                flush=True,
            )

            error_category = _classify_mp_error(result.get("status"), error_code, blocked_by, error_msg)

            if error_category == "CONFIGURATION_ERROR":
                print(
                    f"[MP_SERVICE][{idem_key}] >>> Para soporte de Mercado Pago, X-Request-Id={result.get('request_id')} "
                    f"idempotency-key={idem_key}",
                    flush=True,
                )
                return {
                    "success": False,
                    "message": (
                        "Mercado Pago bloqueó esta operación por política de riesgo/cumplimiento "
                        "de la cuenta (no es un error de tarjeta ni de datos ingresados)."
                    ),
                    "status": result.get("status"),
                    "error": error_msg,
                    "error_code": error_code,
                    "blocked_by": blocked_by,
                    "error_category": error_category,
                    "request_id": result.get("request_id"),
                    "cause": error_causes
                }

            if result.get("status") == 403:
                return {
                    "success": False,
                    "message": "Pago no autorizado por Mercado Pago (UNAUTHORIZED). Revisa las credenciales, el modo Sandbox/Production y configura la cuenta correctamente.",
                    "status": 403,
                    "error_category": "AUTHENTICATION_ERROR",
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

                retry_result = self._create_payment(fallback_data, request_options)
                print(f"[MP_SERVICE][{idem_key}] [CARD] Reintento fallback status={retry_result.get('status')}", flush=True)
                if retry_result.get("status") == 201:
                    retry_response = retry_result["response"]
                    resultado = self._result_from_payment_response(retry_response)
                    print(f"[MP_SERVICE][{idem_key}] [CARD] Reintento fallback clasificado: status={resultado.get('status')} success={resultado.get('success')}", flush=True)
                    return resultado

                fallback_response = retry_result.get("response", {})
                print(f"[MP_SERVICE][{idem_key}] [CARD] Reintento fallback result: {_sanitize_for_log(fallback_response)}", flush=True)
                fallback_msg = fallback_response.get("message", error_msg)
                return {
                    "success": False,
                    "message": fallback_msg,
                    "status": retry_result.get("status"),
                    "error": fallback_msg,
                    "error_category": _classify_mp_error(
                        retry_result.get("status"), fallback_response.get("code"),
                        fallback_response.get("blocked_by"), fallback_msg,
                    ),
                    "cause": fallback_response.get("cause", error_causes)
                }

            return {
                "success": False,
                "message": error_msg,
                "status": result.get("status"),
                "error": error_msg,
                "error_category": error_category,
                "cause": error_causes
            }

        except Exception as e:
            print(f"[MP_SERVICE][{idem_key}] [ERROR] Excepcion: {type(e).__name__}: {str(e)}", flush=True)
            import traceback
            traceback.print_exc()
            return {"success": False, "message": str(e), "error": str(e)}


# Instancia global
mercado_pago_service = MercadoPagoService()
