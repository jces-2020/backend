# -*- coding: utf-8 -*-
"""
Controlador para procesar pagos con otros métodos (PagoEfectivo, etc.)
"""

from flask import Blueprint, request, jsonify
import mercadopago
import os
import uuid
from mercadopago import config
from dotenv import load_dotenv

load_dotenv()

# Importar utilidad de JWT
try:
    from app.controllers.clientes_controller import verify_jwt
except ImportError:
    from controllers.clientes_controller import verify_jwt

otros_metodos_bp = Blueprint('otros_metodos_pago', __name__)


@otros_metodos_bp.route("/api/pagos/procesar_otros_metodos", methods=["POST", "OPTIONS"])
def procesar_otros_metodos():
    """Procesa pagos con otros métodos (PagoEfectivo, etc.) sin token de tarjeta"""
    if request.method == "OPTIONS":
        return jsonify({"success": True}), 200
    
    try:
        # Validar JWT
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"success": False, "message": "Token no proporcionado"}), 401

        token = auth_header.split(" ", 1)[1]
        payload = verify_jwt(token)
        if not payload:
            return jsonify({"success": False, "message": "Token inválido"}), 401

        data = request.get_json() or {}

        # Extraer datos del pago
        transaction_amount = data.get("transaction_amount")
        payment_method_id = data.get("payment_method_id")
        description = data.get("description")
        carrito_id = data.get("carrito_id")
        cliente_id = data.get("cliente_id")
        payer = data.get("payer", {})

        # Validar datos requeridos
        if not all([transaction_amount, payment_method_id, carrito_id, cliente_id, payer.get("email")]):
            return jsonify({
                "success": False,
                "message": "Datos incompletos"
            }), 400

        # Validar que el cliente del token coincida
        cliente_id_token = payload.get("sub")
        if cliente_id != cliente_id_token:
            return jsonify({"success": False, "message": "No autorizado"}), 403

        # Inicializar SDK de Mercado Pago
        access_token = os.getenv("MERCADO_PAGO_ACCESS_TOKEN")
        if not access_token:
            return jsonify({
                "success": False,
                "message": "Configuración de Mercado Pago no disponible"
            }), 500

        sdk = mercadopago.SDK(access_token)

        # Preparar datos del pago
        payment_data = {
            "transaction_amount": float(transaction_amount),
            "description": description,
            "payment_method_id": payment_method_id,
            "payer": {
                "email": payer.get("email"),
                "first_name": payer.get("first_name"),
                "last_name": payer.get("last_name"),
                "identification": {
                    "type": payer.get("identification", {}).get("type", "DNI"),
                    "number": payer.get("identification", {}).get("number", "00000000")
                }
            },
            "external_reference": carrito_id
        }

        # Configurar idempotencia
        request_options = config.RequestOptions()
        request_options.custom_headers = {
            "x-idempotency-key": str(uuid.uuid4())
        }

        print(f"[OTROS_METODOS] Procesando pago...")
        print(f"[OTROS_METODOS] Método: {payment_method_id}")
        print(f"[OTROS_METODOS] Monto: {transaction_amount}")
        print(f"[OTROS_METODOS] Payment Data: {payment_data}")

        # Crear pago con Mercado Pago
        result = sdk.payment().create(payment_data, request_options)
        print(f"[OTROS_METODOS] Respuesta: {result}")

        if result.get("status") == 201:
            response = result["response"]
            external_url = response.get("transaction_details", {}).get("external_resource_url")
            
            print(f"[OTROS_METODOS] ✅ Pago creado: {response.get('id')}")
            if external_url:
                print(f"[OTROS_METODOS] URL externa: {external_url}")

            respuesta = {
                "success": True,
                "payment_id": response.get("id"),
                "status": response.get("status"),
                "status_detail": response.get("status_detail"),
                "external_resource_url": external_url,
                "transaction_details": response.get("transaction_details")
            }
            
            print(f"[OTROS_METODOS] Enviando respuesta: {respuesta}")

            return jsonify(respuesta), 200

        # Si el pago no fue exitoso
        return jsonify({
            "success": False,
            "message": "Pago rechazado",
            "error": result.get("response", {}).get("message"),
            "cause": result.get("response", {}).get("cause")
        }), 400

    except Exception as e:
        print(f"[OTROS_METODOS] ❌ Error: {e}")
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500
