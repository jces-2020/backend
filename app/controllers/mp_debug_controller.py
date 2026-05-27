# -*- coding: utf-8 -*-
"""
Debug de Mercado Pago - Obtener usuarios de prueba válidos
"""
from flask import Blueprint, jsonify
import os
import requests

mp_debug_bp = Blueprint("mp_debug", __name__)

@mp_debug_bp.route("/api/mp/test_users", methods=["GET"])
def get_test_users():
    """Obtiene los usuarios de prueba asociados a tu access token"""
    try:
        access_token = os.environ.get("MERCADO_PAGO_ACCESS_TOKEN")
        
        if not access_token:
            return jsonify({"error": "Access token no configurado"}), 500
        
        # Obtener info del usuario actual
        url = "https://api.mercadopago.com/users/me"
        headers = {"Authorization": f"Bearer {access_token}"}
        
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            data = response.json()
            return jsonify({
                "success": True,
                "user_id": data.get("id"),
                "email": data.get("email"),
                "site_id": data.get("site_id"),
                "test_user": data.get("test_user", False),
                "info": "Este es el usuario asociado a tu access token",
                "email_correcto": data.get("email")
            }), 200
        else:
            return jsonify({
                "success": False,
                "error": response.text,
                "status": response.status_code
            }), response.status_code
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@mp_debug_bp.route("/api/mp/list_test_users", methods=["GET"])
def list_test_users():
    """Lista TODOS los usuarios de prueba creados en tu cuenta"""
    try:
        access_token = os.environ.get("MERCADO_PAGO_ACCESS_TOKEN")
        
        if not access_token:
            return jsonify({"error": "Access token no configurado"}), 500
        
        # Endpoint para listar test users
        url = "https://api.mercadopago.com/users/test_user/search"
        headers = {"Authorization": f"Bearer {access_token}"}
        
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            users = response.json()
            
            # Buscar el usuario de tipo BUYER (comprador)
            buyer_users = [u for u in users if u.get("site_id") == "MPE"]
            
            return jsonify({
                "success": True,
                "test_users": users,
                "buyer_users": buyer_users,
                "total": len(users),
                "recomendacion": "Usa el email de un usuario con site_status='active'"
            }), 200
        else:
            return jsonify({
                "success": False,
                "error": response.text,
                "status": response.status_code,
                "hint": "Si falla, crea usuarios de prueba en: https://www.mercadopago.com.pe/developers/panel/test-users"
            }), response.status_code
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500
