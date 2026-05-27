from flask import Blueprint, jsonify
import mercadopago

mp_verificar_bp = Blueprint('mp_verificar', __name__)

# TUS CREDENCIALES
ACCESS_TOKEN = "TEST-1412542350445034-011500-d6f20366d5ae9b143e38bba9d53ff7b2-3135079821"

@mp_verificar_bp.route("/verificar_pago/<payment_id>", methods=["GET"])
def verificar_pago(payment_id):
    """Consulta un pago directamente a Mercado Pago para verificar que existe"""
    try:
        sdk = mercadopago.SDK(ACCESS_TOKEN)
        
        # Consultar el pago directamente a la API de MP
        result = sdk.payment().get(payment_id)
        
        if result.get("status") == 200:
            pago = result["response"]
            return jsonify({
                "existe": True,
                "payment_id": pago["id"],
                "status": pago["status"],
                "status_detail": pago["status_detail"],
                "transaction_amount": pago["transaction_amount"],
                "date_approved": pago.get("date_approved"),
                "authorization_code": pago.get("authorization_code"),
                "payer_email": pago["payer"]["email"],
                "respuesta_completa": pago
            }), 200
        else:
            return jsonify({
                "existe": False,
                "mensaje": "Pago no encontrado en Mercado Pago"
            }), 404
            
    except Exception as e:
        return jsonify({
            "error": str(e)
        }), 500
