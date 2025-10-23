from flask import Blueprint, request, jsonify
import datetime
import json
import os
import requests
from services.agent_service import AgentService
from services.update_service import (
    actualizar_ticket,
    get_ticket_latest_article,
    get_or_create_session_id,
)

agent_bp = Blueprint("agent", __name__)
service = AgentService()


@agent_bp.route("/agent/update", methods=["POST"])
def update_with_diagnosis():
    """Actualiza un ticket en Znuny generando diagnóstico automáticamente."""
    from services.update_service import (
        get_or_create_session_id,
        get_ticket_latest_article,
        actualizar_ticket,
    )

    data = request.get_json() or {}
    ticket_id = data.get("ticket_id")
    session_id = data.get("session_id")

    if not ticket_id:
        return jsonify({"error": "Debe enviar 'ticket_id'"}), 400

    # Si no se pasa session_id, obtenerlo automáticamente
    if not session_id:
        try:
            session_id = get_or_create_session_id()
            print(f"[Agent] ✅ Obtenido SessionID automáticamente: {session_id[:10]}...")
        except Exception as e:
            return jsonify({"error": f"No se pudo obtener SessionID: {e}"}), 500

    # Parámetros opcionales
    titulo = data.get("titulo") or f"Actualización ticket {ticket_id}"
    usuario = data.get("usuario") or ""
    queue_id = data.get("queue_id") or 1
    priority_id = data.get("priority_id") or 3
    state_id = data.get("state_id") or 4
    subject = data.get("subject") or "Actualización desde API"
    body = data.get("body")
    ticket_text = data.get("ticket_text")

    # Obtener texto del ticket si no se pasó body ni ticket_text
    if not body and not ticket_text:
        ticket_text = get_ticket_latest_article(ticket_id, session_id)

    if not ticket_text and not body:
        return jsonify({
            "error": "No se encontró texto del ticket ni se envió 'body'."
        }), 400

    # Generar diagnóstico si no se pasó body explícito
    if not body:
        try:
            print("[Agent] Generando diagnóstico a partir del ticket...")
            body = service.diagnose_ticket(ticket_text)
        except Exception as e:
            return jsonify({"error": f"Fallo al generar diagnóstico: {e}"}), 500

    # Actualizar ticket con el diagnóstico
    try:
        print(f"[Agent] Enviando actualización a ticket {ticket_id}...")
        resp = actualizar_ticket(
            ticket_id=ticket_id,
            session_id=session_id,
            titulo=titulo,
            usuario=usuario,
            queue_id=queue_id,
            priority_id=priority_id,
            state_id=state_id,
            subject=subject,
            body=body,
        )
        return jsonify({
            "ok": True,
            "ticket_id": ticket_id,
            "diagnosis": body,
            "update_response": resp
        })
    except Exception as e:
        return jsonify({"error": f"Error actualizando el ticket: {e}"}), 500


@agent_bp.route("/znuny-webhook", methods=["POST", "GET", "PUT"])
def znuny_webhook():
    """Recibe webhooks desde Znuny y encadena actualización automática."""
    payload = {
        "time": datetime.datetime.utcnow().isoformat() + "Z",
        "method": request.method,
        "headers": dict(request.headers),
        "args": request.args.to_dict(),
        "json": request.get_json(silent=True),
        "form": request.form.to_dict(),
        "raw_body": request.get_data(as_text=True),
    }

    # Guardar log
    logs_dir = os.path.join(os.path.abspath(os.path.dirname(__file__)), "..", "logs")
    os.makedirs(logs_dir, exist_ok=True)
    log_file = os.path.join(logs_dir, "znuny_requests.log")
    try:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n\n")
    except Exception:
        pass

    print(json.dumps(payload, ensure_ascii=False, indent=2))

    # Intentar obtener TicketID
    ticket_id = None
    payload_json = payload.get("json") or {}
    if isinstance(payload_json, dict):
        ticket_id = (
            payload_json.get("TicketID")
            or payload_json.get("ticket_id")
            or (payload_json.get("Ticket") or {}).get("TicketID")
        )

    # Si no hay TicketID, intentar del último log
    if not ticket_id:
        try:
            with open(log_file, "r", encoding="utf-8") as f:
                entries = [e.strip() for e in f.read().split("\n\n") if e.strip()]
            for raw in reversed(entries):
                try:
                    obj = json.loads(raw)
                    pj = obj.get("json") or {}
                    ticket_id = (
                        pj.get("TicketID")
                        or pj.get("ticket_id")
                        or (pj.get("Ticket") or {}).get("TicketID")
                    )
                    if ticket_id:
                        break
                except Exception:
                    continue
        except Exception:
            pass

    if not ticket_id:
        return jsonify({"error": "No se encontró TicketID en el payload"}), 400

    # Obtener o crear SessionID
    session_id = (
        os.environ.get("ZNUNY_SESSION_ID")
        or os.environ.get("SESSION_ID")
        or payload_json.get("SessionID")
        or get_or_create_session_id()
    )

    # Encadenar actualización
    try:
        update_url = "http://127.0.0.1:5000/agent/update"
        resp = requests.post(update_url, json={
            "ticket_id": str(ticket_id),
            "session_id": str(session_id)
        }, timeout=15)
        print(f"[Webhook] /agent/update → {resp.status_code}")
    except Exception as e:
        print(f"[Webhook] Error al llamar /agent/update: {e}")

    return jsonify({"status": "ok", "ticket_id": ticket_id}), 200
