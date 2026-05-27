# -*- coding: utf-8 -*-
"""
Proxy hacia el microservicio backend-etl-dashboard (puerto 5002).
El frontend llama a /api/etl/* → este controller reenvía al ETL backend.
"""
import os
import requests
from flask import Blueprint, request, jsonify, Response, make_response

etl_proxy_bp = Blueprint('etl_proxy', __name__)

ETL_BASE = os.getenv('ETL_BACKEND_URL', 'http://localhost:5002')
TIMEOUT  = 60  # segundos — el ETL puede tardar en procesar


def _forward(method: str, path: str, **kwargs) -> Response:
    """Reenvía la petición al ETL backend y devuelve la respuesta."""
    url = f"{ETL_BASE}{path}"
    try:
        resp = requests.request(method, url, timeout=TIMEOUT, **kwargs)
        # Si es archivo (Excel), propaga el contenido binario directamente
        content_type = resp.headers.get('Content-Type', 'application/json')
        if 'spreadsheet' in content_type or 'octet-stream' in content_type:
            response = make_response(resp.content)
            response.status_code = resp.status_code
            response.headers['Content-Type'] = content_type
            response.headers['Content-Disposition'] = resp.headers.get('Content-Disposition', '')
            response.headers['Access-Control-Allow-Origin'] = '*'
            response.headers['Access-Control-Expose-Headers'] = 'Content-Disposition'
            return response
        return jsonify(resp.json()), resp.status_code
    except requests.exceptions.ConnectionError:
        return jsonify({"error": "ETL backend no disponible", "detail": f"No se pudo conectar a {ETL_BASE}"}), 503
    except requests.exceptions.Timeout:
        return jsonify({"error": "ETL backend tardó demasiado", "detail": "Timeout al procesar el dashboard"}), 504
    except Exception as e:
        return jsonify({"error": "Error interno del proxy ETL", "detail": str(e)}), 500


# ── ETL tables ──────────────────────────────────────────────────

@etl_proxy_bp.route('/api/etl/tables', methods=['GET'])
def etl_tables():
    return _forward('GET', '/api/etl/tables')


@etl_proxy_bp.route('/api/etl/tables/stats', methods=['GET'])
def etl_tables_stats():
    return _forward('GET', '/api/etl/tables/stats')


@etl_proxy_bp.route('/api/etl/tables/<string:table_name>/preview', methods=['GET'])
def etl_table_preview(table_name):
    rows = request.args.get('rows', '10')
    return _forward('GET', f'/api/etl/tables/{table_name}/preview?rows={rows}')


@etl_proxy_bp.route('/api/etl/tables/<string:table_name>/export', methods=['GET'])
def etl_table_export(table_name):
    return _forward('GET', f'/api/etl/tables/{table_name}/export')


# ── Dashboard ────────────────────────────────────────────────────

@etl_proxy_bp.route('/api/etl/dashboard/templates', methods=['GET'])
def etl_dashboard_templates():
    return _forward('GET', '/api/dashboard/templates')


@etl_proxy_bp.route('/api/etl/dashboard/generate', methods=['POST'])
def etl_dashboard_generate():
    return _forward('POST', '/api/dashboard/generate', json=request.get_json())


@etl_proxy_bp.route('/api/etl/dashboard/export', methods=['POST'])
def etl_dashboard_export():
    """Solicita el Excel al ETL backend y lo reenvía al frontend."""
    return _forward('POST', '/api/dashboard/export', json=request.get_json())


@etl_proxy_bp.route('/api/etl/health', methods=['GET'])
def etl_health():
    return _forward('GET', '/health')


# ── Minería de Datos ─────────────────────────────────────────────

@etl_proxy_bp.route('/api/etl/mining/rfm', methods=['GET'])
def etl_mining_rfm():
    return _forward('GET', '/api/mining/rfm')


@etl_proxy_bp.route('/api/etl/mining/forecast', methods=['GET'])
def etl_mining_forecast():
    meses = request.args.get('meses', '3')
    return _forward('GET', f'/api/mining/forecast?meses={meses}')


@etl_proxy_bp.route('/api/etl/mining/clustering', methods=['GET'])
def etl_mining_clustering():
    k = request.args.get('k', '3')
    return _forward('GET', f'/api/mining/clustering?k={k}')


@etl_proxy_bp.route('/api/etl/mining/correlaciones', methods=['GET'])
def etl_mining_correlaciones():
    return _forward('GET', '/api/mining/correlaciones')


@etl_proxy_bp.route('/api/etl/mining/anomalias', methods=['GET'])
def etl_mining_anomalias():
    return _forward('GET', '/api/mining/anomalias')
