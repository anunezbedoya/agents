from flask import Blueprint, request, jsonify
from services.agent_service import AgentService

agent_bp = Blueprint("agent", __name__)
service = AgentService()

@agent_bp.route("/agent/diagnostico", methods=["POST"])
def diagnostico():
    data = request.get_json()
    ticket_text = data.get("ticket_text")

    if not ticket_text:
        return jsonify({"error": "Debe enviar el texto del ticket"}), 400

    try:
        resultado = service.diagnose_ticket(ticket_text)
        return jsonify({"diagnostico": resultado})
    except Exception as e:
        return jsonify({"error": str(e)}), 500