from flask import Blueprint, request, jsonify
import datetime
import json
import os
# Importa solo lo necesario para el controlador
from services.update_service import (
    update_ticket_with_auto_diagnosis, 
    get_or_create_session_id,
)

agent_bp = Blueprint("agent", __name__)


# --------------------------------------------------------------------------
## Endpoint: Actualización Manual (/agent/update)
# --------------------------------------------------------------------------
@agent_bp.route("/agent/update", methods=["POST"])
def update_with_diagnosis():
    """Endpoint HTTP que delega la actualización y el diagnóstico al servicio."""
    
    data = request.get_json() or {}
    ticket_id = data.get("ticket_id")

    if not ticket_id:
        return jsonify({"error": "Debe enviar 'ticket_id'"}), 400

    try:
        # LLAMADA DIRECTA A LA LÓGICA CENTRAL
        result = update_ticket_with_auto_diagnosis(
            ticket_id=ticket_id, 
            session_id=data.get("session_id"), 
            data=data
        )
        return jsonify(result), 200
        
    except ValueError as e:
        print(f"[ERROR] Validación de datos fallida: {e}")
        return jsonify({"error": f"Error de datos: {e}"}), 400
    except RuntimeError as e:
        print(f"[ERROR] Fallo en la comunicación con Znuny: {e}")
        return jsonify({"error": f"Error de servicio Znuny: {e}"}), 500
    except Exception as e:
        print(f"[ERROR] Error interno inesperado: {e}")
        return jsonify({"error": f"Error interno inesperado: {e}"}), 500


# --------------------------------------------------------------------------
## Endpoint: Webhook de Znuny (/znuny-webhook)
# --------------------------------------------------------------------------
@agent_bp.route("/znuny-webhook", methods=["POST", "GET", "PUT"])
def znuny_webhook():
    """Recibe webhooks desde Znuny y encadena actualización automática (delegando)."""
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

    # Lógica para obtener TicketID 
    ticket_id = None
    payload_json = payload.get("json") or {}
    if isinstance(payload_json, dict):
        # Forma concisa y robusta de buscar TicketID en las ubicaciones más probables
        ticket_id = (
            (payload_json.get("Event") or {}).get("TicketID")
            or (payload_json.get("Ticket") or {}).get("TicketID")
            or payload_json.get("TicketID")
        )

    # Lógica de fallback para TicketID (Se mantiene el chequeo de logs si no se encuentra en el payload)
    if not ticket_id:
        try:
            with open(log_file, "r", encoding="utf-8") as f:
                entries = [e.strip() for e in f.read().split("\n\n") if e.strip()]
            for raw in reversed(entries):
                try:
                    obj = json.loads(raw)
                    pj = obj.get("json") or {}
                    ticket_id = (
                        (pj.get("Event") or {}).get("TicketID")
                        or (pj.get("Ticket") or {}).get("TicketID")
                        or pj.get("TicketID")
                    )
                    if ticket_id: break
                except Exception: continue
        except Exception: pass

    if not ticket_id:
        return jsonify({"error": "No se encontró TicketID en el payload"}), 400

    # -----------------------------------------------------------
    # CORRECCIÓN DE UNBOUNDLOCALERROR: Obtener SessionID de forma explícita
    # -----------------------------------------------------------
    session_id = (
        os.environ.get("ZNUNY_SESSION_ID")
        or os.environ.get("SESSION_ID")
        or payload_json.get("SessionID")
    )
    
    # Si session_id sigue siendo None, forzamos la creación/obtención (llamando a la función)
    if not session_id:
        try:
            session_id = get_or_create_session_id()
            print(f"[Webhook] ✅ SessionID creado/obtenido automáticamente.")
        except Exception as e:
            # Si falla la creación de la sesión (ej. error de autenticación), abortamos.
            return jsonify({"error": f"No se pudo obtener SessionID: {e}"}), 500


    # Encadenar actualización: LLAMADA DIRECTA AL SERVICIO
    try:
        print(f"[Webhook] Procesando ticket {ticket_id}...")
   
        update_ticket_with_auto_diagnosis(
            ticket_id=ticket_id,
            session_id=session_id,
            data=payload_json
        )
        print(f"[Webhook] Actualización de ticket {ticket_id} completada.")
        
    except Exception as e:
        # Maneja cualquier fallo en la lógica central y lo registra.
        print(f"[Webhook] Error al procesar el webhook: {e}")
        return jsonify({"status": "error", "message": f"Fallo en la actualización: {e}"}), 500 

    return jsonify({"status": "ok", "ticket_id": ticket_id}), 200