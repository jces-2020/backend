# -*- coding: utf-8 -*-
"""
Main Flask Application - VidrioBras Backend

Patrón: Factory Method para auto-registro de blueprints
Beneficio: Agregar nuevos endpoints = crear archivo, listo. Sin editar main.py
"""
import sys
import os

# Asegurar que tanto 'backend/app' (para from services.X)
# como 'backend' (para from app.services.X) estén en sys.path
_base = os.path.dirname(os.path.abspath(__file__))          # backend/app
_root = os.path.dirname(_base)                               # backend
for _p in [_base, _root]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

# ===============================
# IMPORTS ESENCIALES
# ===============================
from flask import Flask, render_template, jsonify, request
from flask_cors import CORS
import logging
from dotenv import load_dotenv
import unicodedata
from app.controllers.tipo_personal_controller import verify_jwt

# ===============================
# LOAD ENV
# ===============================
load_dotenv()


# ===============================
# CREAR APP
# ===============================
app = Flask(
    __name__,
    template_folder="templates",
    static_folder="static"
)


# ===============================
# CORS
# ===============================
CORS(app, resources={r"/*": {"origins": "*"}})


# ===============================
# AUTO-REGISTRAR BLUEPRINTS (Factory Pattern)
# ===============================
from app.core import auto_register_blueprints

print("\n" + "=" * 60)
print("AUTO-REGISTRANDO BLUEPRINTS...")
print("=" * 60)
auto_register_blueprints(app)

# Supabase debug
from services.supabase_client import IS_SERVICE, SUPABASE_URL


def _env_enabled(name: str, default: str = "1") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "si")


def _normalize_text(value: str) -> str:
    if not value:
        return ""
    normalized = unicodedata.normalize("NFD", str(value))
    normalized = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
    return normalized.upper().strip()


@app.before_request
def guard_flutter_productos_routes():
    """Protege todas las rutas /api/flutter/productos independientemente del blueprint cargado."""
    if not request.path.startswith('/api/flutter/productos'):
        return None

    if not _env_enabled('FLUTTER_PRODUCTOS_REQUIRE_AUTH', '1'):
        return None

    auth = request.headers.get('Authorization', '')
    if not auth.startswith('Bearer '):
        return jsonify({'success': False, 'message': 'No autorizado: falta token Bearer'}), 401

    token = auth.split(' ', 1)[1]
    payload = verify_jwt(token)
    if not payload or payload.get('aud') != 'personal':
        return jsonify({'success': False, 'message': 'Token inválido o expirado'}), 401

    required_mobile_key = os.getenv('MOBILE_API_KEY', '').strip()
    if required_mobile_key:
        provided_mobile_key = request.headers.get('X-Mobile-Key', '').strip()
        if provided_mobile_key != required_mobile_key:
            return jsonify({'success': False, 'message': 'Acceso denegado: cliente móvil no válido'}), 403

    if request.method.upper() in ('POST', 'PUT', 'PATCH', 'DELETE'):
        area = _normalize_text(payload.get('area', ''))
        if area not in ('ALMACEN', 'ADMINISTRACION'):
            return jsonify({'success': False, 'message': 'Área no autorizada'}), 403

    return None


# ===============================
# RUTAS BASE
# ===============================

@app.route("/ping")
def ping():
    return "pong", 200


@app.route("/")
def root():
    return """
    <h2>Backend VidrioBras</h2>
    <ul>
        <li>/ping</li>
        <li>/test-facturacion</li>
    </ul>
    """


@app.route("/_debug_supabase")
def debug_supabase():

    return jsonify({
        "is_service": bool(IS_SERVICE),
        "supabase_url": SUPABASE_URL
    })


# ===============================
# RUN
# ===============================

if __name__ == "__main__":

    print("====================================")
    print("Servidor iniciado")
    print("Modo APISPERU:", os.getenv("APISPERU_ENV"))
    print("====================================")

    # Iniciar scheduler solo en el proceso principal (no en el reloader de Flask)
    if os.environ.get("WERKZEUG_RUN_MAIN") != "true":
        from services.scheduler import iniciar_scheduler
        iniciar_scheduler()

    quiet_http_logs = os.getenv("QUIET_HTTP_LOGS", "0").strip().lower() in ("1", "true", "yes", "si")
    if quiet_http_logs:
        logging.getLogger("werkzeug").setLevel(logging.ERROR)

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )
