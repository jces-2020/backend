from flask import Blueprint, jsonify

from services.ai_dashboard_service import get_dashboard_counts

ai_dashboard_bp = Blueprint("ai_dashboard_bp", __name__)


@ai_dashboard_bp.route("/api/ai/dashboard", methods=["GET"])
def ai_dashboard():
    counts = get_dashboard_counts()
    return jsonify({"success": True, "counts": counts})
