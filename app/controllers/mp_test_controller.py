# -*- coding: utf-8 -*-
"""
🧪 PRUEBA DE MERCADO PAGO - AISLADO
NO toca el código principal
"""
from flask import Blueprint, render_template, request, jsonify
import mercadopago

mp_test_bp = Blueprint("mp_test", __name__)

# 🔑 CREDENCIALES DE PRODUCCIÓN
ACCESS_TOKEN = "APP_USR-1412542350445034-011500-ab49954346e2593527d195694325fb08-3135079821"
PUBLIC_KEY = "APP_USR-31db4b36-66c5-4017-a197-d65775a236d4"

@mp_test_bp.route("/test_mp", methods=["GET"])
def test_page():
    """Página HTML de prueba"""
    return render_template(
        "mp_test.html", 
        public_key=PUBLIC_KEY,
        test_buyer_email="i2415914@continental.edu.pe"  # Tu email real
    )


@mp_test_bp.route("/test_mp/procesar", methods=["POST"])
def procesar_pago_test():
    """Procesa el pago de prueba"""
    try:
        data = request.get_json()
        
        print(f"[TEST_MP] ========== DATOS RECIBIDOS ==========")
        print(f"[TEST_MP] Token: {data.get('token')}")
        print(f"[TEST_MP] Payment Method ID: {data.get('payment_method_id')}")
        print(f"[TEST_MP] Issuer ID: {data.get('issuer_id')}")
        print(f"[TEST_MP] Email: {data.get('email')}")
        print(f"[TEST_MP] ========================================")
        
        # Validar que el token exista
        if not data.get('token'):
            return jsonify({
                "success": False,
                "error": {
                    "message": "Token de tarjeta no recibido. Verifica la consola del navegador para ver errores del CardForm."
                }
            }), 400
        
        # SDK de Mercado Pago
        sdk = mercadopago.SDK(ACCESS_TOKEN)
        
        payment_data = {
            "transaction_amount": 12.50,  # Monto irregular para evitar filtros antifraude
            "token": data.get("token"),
            "description": "Prueba de pago VIDRIOBRAS",
            "installments": 1,
            "payment_method_id": data.get("payment_method_id"),
            "payer": {
                "email": data.get("email")
            }
        }
        
        # Issuer opcional
        if data.get("issuer_id"):
            payment_data["issuer_id"] = data.get("issuer_id")
        
        print(f"[TEST_MP] Procesando pago...")
        print(f"[TEST_MP] Payment Data completo: {payment_data}")
        
        result = sdk.payment().create(payment_data)
        
        print(f"[TEST_MP] Respuesta: {result}")
        
        if result.get("status") == 201:
            response = result["response"]
            payment_status = response.get("status")
            payment_detail = response.get("status_detail")
            
            # ✅ VERIFICAR ESTADO DEL PAGO
            if payment_status in ["approved", "in_process"]:
                # approved = aprobado inmediatamente
                # in_process = en revisión manual (común en producción)
                return jsonify({
                    "success": True,
                    "payment_id": response["id"],
                    "status": payment_status,
                    "status_detail": payment_detail,
                    "message": "Pago aprobado" if payment_status == "approved" else "Pago en revisión"
                }), 200
            else:
                # ❌ PAGO RECHAZADO O PENDIENTE DE ACCIÓN
                return jsonify({
                    "success": False,
                    "payment_id": response["id"],
                    "status": payment_status,
                    "status_detail": payment_detail,
                    "message": f"Pago {payment_status}: {payment_detail}"
                }), 400
        else:
            return jsonify({
                "success": False,
                "error": result.get("response", {})
            }), 400
            
    except Exception as e:
        print(f"[TEST_MP] Error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
