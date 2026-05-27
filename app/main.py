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
from flask import Flask, render_template, jsonify
from flask_cors import CORS
import logging
from dotenv import load_dotenv

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
