import os
import time
import json
import requests
# Asumo que AgentService está en un módulo llamado .agent_service
from .agent_service import AgentService 


# --------------------------------------------------------------------------
# CONFIGURACIÓN Y CACHÉ DE SESIÓN
# --------------------------------------------------------------------------
_AGENT_SERVICE = AgentService() # Instancia del servicio de diagnóstico
_CACHED_SESSION_ID = None
_CACHED_SESSION_TS = 0.0
_SESSION_TTL_SECONDS = int(os.environ.get("ZNUNY_SESSION_TTL", "3300"))


# --------------------------------------------------------------------------
# AUTENTICACIÓN Y SESIÓN
# --------------------------------------------------------------------------
def _login_create_session() -> str:
    """Crea un nuevo SessionID autenticando contra Znuny."""
    user = os.environ.get("ZNUNY_USERNAME")
    password = os.environ.get("ZNUNY_PASSWORD")
    base_url = os.environ.get("ZNUNY_BASE_API")

    if not all([user, password, base_url]):
        raise RuntimeError("Faltan variables de entorno requeridas: ZNUNY_USERNAME, ZNUNY_PASSWORD o ZNUNY_BASE_API")

    url = f"{base_url.rstrip('/')}/Session"
    payload = {"UserLogin": user, "Password": password}
    headers = {
        "Content-Type": "application/json; charset=UTF-8",
        "Accept": "application/json",
        "Accept-Encoding": "identity",
        "User-Agent": "curl/7.81.0",
    }

    try:
        resp = requests.patch(
            url,
            data=json.dumps(payload),
            headers=headers,
            timeout=10
        )
        resp.raise_for_status()
        data = resp.json()
        
        session_id = data.get("SessionID")

        if not session_id:
            raise RuntimeError(f"Znuny no devolvió SessionID. Respuesta: {data}")

        return session_id
        
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Error de conexión al autenticar: {e}")


def get_or_create_session_id() -> str:
    """Obtiene o genera un SessionID válido, usando cache en memoria."""
    global _CACHED_SESSION_ID, _CACHED_SESSION_TS

    env_sid = os.environ.get("ZNUNY_SESSION_ID") or os.environ.get("SESSION_ID")
    if env_sid:
        return env_sid

    now = time.time()
    if _CACHED_SESSION_ID and (now - _CACHED_SESSION_TS) < _SESSION_TTL_SECONDS:
        return _CACHED_SESSION_ID

    _CACHED_SESSION_ID = _login_create_session()
    _CACHED_SESSION_TS = now
    return _CACHED_SESSION_ID


# --------------------------------------------------------------------------
# OBTENCIÓN DE DATOS
# --------------------------------------------------------------------------
def get_ticket_latest_article(ticket_id: int, session_id: str) -> str | None:
    """Obtiene el texto del último artículo de un ticket en Znuny."""
    def _extract_body(articles):
        if not isinstance(articles, list) or not articles:
            return None
        # Ordena por CreateTime o ArticleID (como fallback) y toma el último
        last = sorted(
            articles,
            key=lambda a: a.get("CreateTime") or a.get("ArticleID") or 0
        )[-1]
        return last.get("Body")

    base = os.environ.get("ZNUNY_BASE_API", "").rstrip("/")
    headers = {"Accept": "application/json"}

    # Intentar con Ticket/{id}?AllArticles=1
    try:
        url_ticket = f"{base}/Ticket/{ticket_id}?SessionID={session_id}&AllArticles=1"
        r = requests.get(url_ticket, headers=headers, timeout=10)
        r.raise_for_status() # Lanza excepción si hay un error HTTP (4xx o 5xx)
        data = r.json()
        ticket_data = data.get("Ticket")
        if isinstance(ticket_data, list):
            ticket_data = ticket_data[0]
        articles = ticket_data.get("Article") if ticket_data else None
        
        return _extract_body(articles)

    except requests.exceptions.RequestException as e:
        print(f"[ERROR] Fallo al obtener el artículo del ticket {ticket_id}: {e}")
        # En este caso, simplemente retornamos None si falla la obtención del texto.
        return None
    except Exception as e:
        print(f"[ERROR] Error inesperado al procesar artículos de Znuny: {e}")
        return None


# --------------------------------------------------------------------------
# ACTUALIZACIÓN DE TICKET
# --------------------------------------------------------------------------
def actualizar_ticket(ticket_id, session_id, titulo, usuario, queue_id, priority_id, state_id, subject, body, dynamic_fields=None):
    """Actualiza un ticket en Znuny agregando un nuevo artículo."""
    base_url = os.environ.get("ZNUNY_BASE_API", "").rstrip("/")
    url = f"{base_url}/Ticket/{ticket_id}"
    payload = {
        "SessionID": session_id,
        "TicketID": ticket_id,
        "Ticket": {
            "Title": titulo,
            "CustomerUser": usuario,
            "QueueID": queue_id,
            "PriorityID": priority_id,
            "StateID": state_id
        },
        "Article": {
            "Subject": subject,
            "Body": body,
            "ContentType": "text/plain; charset=utf8"
        }
    }

    if dynamic_fields:
        payload["Ticket"]["DynamicFields"] = dynamic_fields

    try:
        r = requests.patch(
            url,
            headers={"Content-Type": "application/json"},
            json=payload,
            timeout=10
        )
        r.raise_for_status()
        return r.json()
    except requests.exceptions.RequestException as e:
        # Devuelve un dict de error que la función orquestadora manejará
        return {"error": str(e)}


# --------------------------------------------------------------------------
# FUNCIÓN DE ORQUESTACIÓN (LA LÓGICA CENTRAL)
# --------------------------------------------------------------------------

def update_ticket_with_auto_diagnosis(ticket_id: int, session_id: str = None, data: dict = None):
    """
    Orquesta la obtención de datos, generación de diagnóstico y actualización del ticket.
    Es la lógica central usada por todos los endpoints.
    """
    data = data or {}

    # Importación e inicialización local para evitar referencias circulares
    # Esto reemplaza a la variable global _AGENT_SERVICE
    try:
        from .agent_service import AgentService 
        _agent_service = AgentService()
    except ImportError as e:
        # Esto captura el error si AgentService no se encuentra, lo que es un error de configuración crítico.
        raise RuntimeError(f"Fallo al cargar AgentService: {e}")

    # 1. Obtener SessionID si no se ha pasado (usa la caché y la creación si es necesario)
    if not session_id:
        # Esto lanzará RuntimeError si falla la autenticación
        # get_or_create_session_id debe ser importada al inicio del archivo update_service.py
        session_id = get_or_create_session_id()
        print(f"[Service] ✅ Obtenido SessionID para la operación.")

    # 2. Parámetros opcionales y valores por defecto
    titulo = data.get("titulo") or f"Actualización ticket {ticket_id}"
    usuario = data.get("usuario") or ""
    queue_id = data.get("queue_id") or 1
    priority_id = data.get("priority_id") or 3
    state_id = data.get("state_id") or 4
    subject = data.get("subject") or "Actualización desde API"
    body = data.get("body")
    ticket_text = data.get("ticket_text")

    # 3. Obtener texto del ticket si no se pasó (y es necesario para el diagnóstico)
    if not body and not ticket_text:
        print(f"[Service] Buscando último artículo del ticket {ticket_id}...")
        # get_ticket_latest_article debe ser importada/definida en este archivo
        ticket_text = get_ticket_latest_article(ticket_id, session_id)

    if not ticket_text and not body:
        # Esto será capturado por el controlador como un 400 (ValueError)
        raise ValueError("No se encontró texto del ticket ni se envió 'body' para el diagnóstico.")

    # 4. Generar diagnóstico si no se pasó body explícito
    if not body:
        try:
            print("[Service] Generando diagnóstico a partir del ticket...")
            # Llama a la instancia local del AgentService
            body = _agent_service.diagnose_ticket(ticket_text)
        except Exception as e:
            # Captura fallos de la API de diagnóstico
            raise RuntimeError(f"Fallo al generar el diagnóstico: {e}")

    # 5. Actualizar ticket
    print(f"[Service] Enviando actualización a ticket {ticket_id}...")
    # actualizar_ticket debe ser importada/definida en este archivo
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
    
    # 6. Manejar errores de actualización de Znuny
    if isinstance(resp, dict) and 'error' in resp:
        # Esto será capturado por el controlador como un 500 (RuntimeError)
        raise RuntimeError(f"Fallo al actualizar Znuny: {resp['error']}")

    return {
        "ok": True,
        "ticket_id": ticket_id,
        "diagnosis": body,
        "update_response": resp
    }