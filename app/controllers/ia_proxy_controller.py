from flask import Blueprint, jsonify, request

from services.ia_proxy_service import ia_chat, ia_health

ia_proxy_bp = Blueprint("ia_proxy_bp", __name__)


@ia_proxy_bp.route("/api/ia/health", methods=["GET"])
def proxy_ia_health():
    try:
        data = ia_health()
        return jsonify(data), 200
    except RuntimeError as exc:
        return jsonify({"success": False, "error": str(exc)}), 503


@ia_proxy_bp.route("/api/ia/chat", methods=["POST"])
def proxy_ia_chat():
    payload = request.get_json(silent=True) or {}

    message = str(payload.get("message", "")).strip()
    messages = payload.get("messages")

    if messages is None:
        messages = [{"role": "user", "content": message}] if message else []

    if not messages:
        return jsonify({"success": False, "error": "Se requiere message o messages."}), 400

    try:
        temperature = float(payload.get("temperature", 0.2))
    except (TypeError, ValueError):
        return jsonify({"success": False, "error": "temperature debe ser numérico."}), 400

    try:
        result = ia_chat(
            messages=messages,
            model=payload.get("model"),
            temperature=temperature,
            system_prompt=payload.get("system_prompt"),
        )
        return jsonify(result), 200
    except RuntimeError as exc:
        return jsonify({"success": False, "error": str(exc)}), 503
