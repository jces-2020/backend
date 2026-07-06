# -*- coding: utf-8 -*-
"""
Main Flask Application - VidrioBras Backend

Patrón: Factory Method para auto-registro de blueprints
Beneficio: Agregar nuevos endpoints = crear archivo, listo. Sin editar main.py
"""
import sys
import os
from datetime import datetime, timezone
import subprocess
import hashlib
import inspect

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


def _detect_git_sha(repo_root: str) -> str:
    """Obtiene el SHA corto de git cuando el repo .git está disponible."""
    try:
        sha = subprocess.check_output(
            ["git", "-C", repo_root, "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL,
            timeout=2,
            text=True,
        ).strip()
        return sha or "unknown"
    except Exception:
        return "unknown"


def _build_info() -> dict:
    """Construye metadata para validar despliegue en runtime."""
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    commit = (
        os.getenv("RELEASE_SHA", "").strip()
        or os.getenv("GITHUB_SHA", "").strip()[:7]
        or _detect_git_sha(repo_root)
    )
    return {
        "service": "vidriobras-backend",
        "commit": commit,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "main_file": os.path.abspath(__file__),
        "cwd": os.getcwd(),
        "repo_root": repo_root,
        "python": sys.version.split()[0],
    }


RUNTIME_BUILD_INFO = _build_info()


def _file_sha256(path: str) -> str:
    """Calcula sha256 de un archivo para verificar versión efectiva en servidor."""
    try:
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except Exception:
        return "unknown"


def _collect_cliente_routes(flask_app: Flask) -> list[str]:
    """Lista rutas de clientes registradas en runtime."""
    return sorted(
        {
            f"{','.join(sorted(rule.methods - {'HEAD', 'OPTIONS'}))} {rule.rule}"
            for rule in flask_app.url_map.iter_rules()
            if rule.rule.startswith('/api/clientes')
        }
    )


def _collect_cliente_route_handlers(flask_app: Flask) -> list[dict]:
    """Devuelve detalle de handlers para rutas /api/clientes* en runtime."""
    rows = []
    for rule in flask_app.url_map.iter_rules():
        if not rule.rule.startswith('/api/clientes'):
            continue
        endpoint = rule.endpoint
        view = flask_app.view_functions.get(endpoint)
        source_file = None
        module_name = None
        qualname = None
        if view is not None:
            module_name = getattr(view, "__module__", None)
            qualname = getattr(view, "__qualname__", None)
            try:
                source_file = inspect.getsourcefile(view) or inspect.getfile(view)
            except Exception:
                source_file = None

        rows.append({
            "rule": rule.rule,
            "methods": sorted(list(rule.methods - {'HEAD', 'OPTIONS'})),
            "endpoint": endpoint,
            "view_module": module_name,
            "view_func": qualname,
            "source_file": source_file,
        })

    rows.sort(key=lambda x: (x["rule"], ",".join(x["methods"])))
    return rows


def _collect_cliente_route_collisions(flask_app: Flask) -> list[dict]:
    """Detecta colisiones de rutas por combinación metodo+rule en /api/clientes*."""
    handlers = _collect_cliente_route_handlers(flask_app)
    bucket = {}
    for row in handlers:
        for method in row.get("methods", []):
            key = f"{method} {row.get('rule')}"
            bucket.setdefault(key, []).append({
                "endpoint": row.get("endpoint"),
                "view_module": row.get("view_module"),
                "view_func": row.get("view_func"),
                "source_file": row.get("source_file"),
            })

    collisions = []
    for key, entries in sorted(bucket.items()):
        if len(entries) > 1:
            collisions.append({
                "route": key,
                "handlers": entries,
            })
    return collisions


RUNTIME_BUILD_INFO["cliente_routes"] = _collect_cliente_routes(app)
RUNTIME_BUILD_INFO["cliente_route_handlers"] = _collect_cliente_route_handlers(app)
RUNTIME_BUILD_INFO["cliente_route_collisions"] = _collect_cliente_route_collisions(app)
RUNTIME_BUILD_INFO["clientes_controller_sha256"] = _file_sha256(
    os.path.join(os.path.dirname(__file__), "controllers", "clientes_controller.py")
)


def _print_runtime_diagnostics(flask_app: Flask) -> None:
    """Imprime diagnostico basico para detectar despliegues apuntando a rutas equivocadas."""
    print("\n" + "=" * 60)
    print("RUNTIME DIAGNOSTICS")
    print("=" * 60)
    print(f"[BOOT] main_file={os.path.abspath(__file__)}")
    print(f"[BOOT] cwd={os.getcwd()}")
    print(f"[BOOT] commit={RUNTIME_BUILD_INFO.get('commit')}")
    print(f"[BOOT] started_at={RUNTIME_BUILD_INFO.get('started_at')}")
    cliente_rules = _collect_cliente_routes(flask_app)
    print(f"[BOOT] clientes_routes={len(cliente_rules)}")
    for r in cliente_rules:
        print(f"[BOOT] route {r}")
    collisions = _collect_cliente_route_collisions(flask_app)
    if collisions:
        print(f"[BOOT][WARN] cliente_route_collisions={len(collisions)}")
        for c in collisions:
            print(f"[BOOT][WARN] collision {c['route']}")
    print("=" * 60 + "\n")


_print_runtime_diagnostics(app)

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

    # El preflight CORS no incluye Authorization; debe pasar sin auth.
    if request.method.upper() == 'OPTIONS':
        response = app.make_response(("", 204))
        response.headers['Access-Control-Allow-Origin'] = request.headers.get('Origin', '*')
        response.headers['Access-Control-Allow-Headers'] = 'Authorization, Content-Type, X-Mobile-Key'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, PATCH, DELETE, OPTIONS'
        return response

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


@app.route("/api/build-info")
def build_info():
    """Devuelve metadata de build para verificar despliegues."""
    return jsonify(RUNTIME_BUILD_INFO), 200


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
