from flask import Blueprint, request, jsonify
import datetime
import json
import os
from services.agent_service import AgentService
from services.update_service import get_or_create_session_id

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

    if not ticket_id:
        return jsonify({"error": "Debe enviar 'ticket_id'"}), 400

    try:
        # Obtener SessionID
        session_id = data.get("session_id") or get_or_create_session_id()
        
        # Parámetros con valores por defecto
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
            return jsonify({"error": "No se encontró texto del ticket ni se envió 'body'."}), 400

        # Generar diagnóstico si no se pasó body explícito
        if not body:
            body = service.diagnose_ticket(ticket_text)

        # Actualizar ticket con el diagnóstico
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
        return jsonify({"error": str(e)}), 500


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

    # Procesar ticket con diagnóstico usando servicios directamente
    try:
        from services.update_service import (
            get_or_create_session_id,
            get_ticket_latest_article,
            actualizar_ticket,
        )
        
        print(f"[Webhook] Procesando ticket {ticket_id} con diagnóstico...")
        
        # Obtener SessionID
        session_id = session_id or get_or_create_session_id()
        
        # Obtener contenido del ticket
        ticket_text = get_ticket_latest_article(ticket_id, session_id)
        
        if not ticket_text:
            return jsonify({
                "status": "error", 
                "ticket_id": ticket_id,
                "error": "No se encontró contenido del ticket"
            }), 400
        
        # Generar diagnóstico
        diagnosis = service.diagnose_ticket(ticket_text)
        
        # Actualizar ticket
        resp = actualizar_ticket(
            ticket_id=ticket_id,
            session_id=session_id,
            titulo=f"Actualización ticket {ticket_id}",
            usuario="",
            queue_id=1,
            priority_id=3,
            state_id=4,
            subject="Actualización desde API",
            body=diagnosis,
        )
        
        print(f"[Webhook] ✅ Ticket {ticket_id} procesado exitosamente")
        return jsonify({
            "status": "ok", 
            "ticket_id": ticket_id,
            "diagnosis": diagnosis,
            "update_response": resp
        }), 200
    except Exception as e:
        print(f"[Webhook] ❌ Error procesando ticket {ticket_id}: {e}")
        return jsonify({
            "status": "error", 
            "ticket_id": ticket_id,
            "error": str(e)
        }), 500
