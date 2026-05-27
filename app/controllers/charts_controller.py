"""
Controlador para servir gráficos matplotlib al frontend.
Los gráficos se generan bajo demanda y se retornan como base64.
"""

from flask import Blueprint, jsonify
from services.charts_service import get_all_dashboard_charts

charts_bp = Blueprint('charts', __name__)


@charts_bp.route('/api/charts/dashboard', methods=['GET'])
def get_dashboard_charts():
    """
    Retorna todos los gráficos del dashboard como base64.
    
    Response:
    {
        "success": true,
        "charts": {
            "summary_bars": "data:image/png;base64,...",
            "products_by_cat": "data:image/png;base64,...",
            "clients_chart": "data:image/png;base64,..."
        }
    }
    """
    try:
        charts = get_all_dashboard_charts()
        
        # Convertir a data URLs
        charts_data = {}
        for key, chart_b64 in charts.items():
            if chart_b64:
                charts_data[key] = f"data:image/png;base64,{chart_b64}"
            else:
                charts_data[key] = None
        
        return jsonify({
            'success': True,
            'charts': charts_data
        }), 200
    except Exception as e:
        print(f"Error en get_dashboard_charts: {e}")
        return jsonify({
            'success': False,
            'message': f'Error al generar gráficos: {str(e)}'
        }), 500
