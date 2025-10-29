import os
import time
import json
import requests
from .agent_service import AgentService 

try:
    _AGENT_SERVICE = AgentService() 
except ImportError as e:
    # Esto asegura que si el archivo AgentService falta, la aplicación falle 
    # inmediatamente al iniciar, no durante un webhook.
    raise RuntimeError(f"Fallo al cargar AgentService: {e}")

# --------------------------------------------------------------------------
# CONFIGURACIÓN Y CACHÉ DE SESIÓN
# --------------------------------------------------------------------------

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
    """
    Obtiene el texto del artículo más relevante (asumiendo que el último es una notificación)
    de un ticket en Znuny, combinando Asunto y Cuerpo para la IA.
    """
       
    def _extract_relevant_text(articles):
        if not isinstance(articles, list) or not articles:
            return None

        # Ya no se realiza ningún filtrado. Se usan todos los artículos.
        relevant_articles = articles 

        # 1. ORDENAR LOS ARTÍCULOS:
        # Ordenamos los artículos por fecha/ID
        sorted_articles = sorted(
            relevant_articles,
            key=lambda a: a.get("CreateTime") or a.get("ArticleID") or 0
        )
        
        # 2. SELECCIONAR EL ARTÍCULO RELEVANTE (Lógica de -2 con red de seguridad):
        
        # Debe haber al menos un artículo para continuar
        if not sorted_articles:
            return None
            
        # Si la lista tiene 2 o más artículos, asumimos que el último es la notificación 
        # y tomamos el penúltimo (-2).
        if len(sorted_articles) >= 2:
            last_relevant = sorted_articles[-2] 
        else:
            # Si solo tiene 1 artículo (o 0, aunque ya se filtró), tomamos el único artículo (-1).
            last_relevant = sorted_articles[-1]
        
        # 3. COMBINAR: Combina el Asunto y el Cuerpo.
        subject = last_relevant.get("Subject", "")
        body = last_relevant.get("Body", "")
        
        if not subject and not body:
            return None
        
        # Retorna el texto combinado
        return f"Asunto: {subject}\n---\nQueja/Cuerpo del artículo:\n{body}"


    base = os.environ.get("ZNUNY_BASE_API", "").rstrip("/")
    headers = {"Accept": "application/json"}

    # Intentar con Ticket/{id}?AllArticles=1
    try:
        url_ticket = f"{base}/Ticket/{ticket_id}?SessionID={session_id}&AllArticles=1"
        r = requests.get(url_ticket, headers=headers, timeout=10)
        r.raise_for_status() 
        data = r.json()
        
        ticket_data = data.get("Ticket")
        if isinstance(ticket_data, list):
            ticket_data = ticket_data[0]
            
        articles = ticket_data.get("Article") if ticket_data else None
        
        return _extract_relevant_text(articles) 

    except requests.exceptions.RequestException as e:
        print(f"[ERROR] Fallo al obtener el artículo del ticket {ticket_id}: {e}")
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
    
    print("\n--- DEBUG: PAYLOAD DE ACTUALIZACIÓN ENVIADO A ZNUNY ---")
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    print("----------------------------------------------------------\n")

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
    Siempre obtiene el último artículo del ticket desde Znuny para generar un diagnóstico.
    """
    data = data or {}
    diagnosis_body = None  

    # 1. Preparación del Agente (Referencia al agente global)
    global _AGENT_SERVICE 
    
    # 2. Obtener SessionID
    if not session_id:
        session_id = get_or_create_session_id()
        print(f"[Service] ✅ Obtenido SessionID para la operación.")

    # 3. Inicialización de Parámetros
    titulo = data.get("titulo") or f"Actualización ticket {ticket_id}"
    usuario = data.get("usuario") or ""
    queue_id = data.get("queue_id") or 1
    priority_id = data.get("priority_id") or 3
    state_id = data.get("state_id") or 4
    subject = data.get("subject") or "Diagnóstico Automático (IA)"

    # 4. Obtener Texto de Origen y Generar Diagnóstico (Siempre se ejecuta)
    
    # A. Obtener texto del ticket (SOLO desde Znuny)
    
    # Inicialización limpia antes de buscar
    ticket_text = None 
    
    print(f"[Service] Buscando último artículo del ticket {ticket_id}...")
    # Llamada obligatoria a la API de Znuny para obtener el texto de origen
    ticket_text = get_ticket_latest_article(ticket_id, session_id)

    if not ticket_text:
        # ERROR CRÍTICO si la API de Znuny no devuelve contenido.
        raise ValueError("No se encontró texto del ticket (último artículo) para generar el diagnóstico.")
        
    # B. Generar Diagnóstico con IA
    try:
        print("[Service] Generando diagnóstico a partir del ticket...")
        
        # USO DEL SERVICIO GLOBAL:
        diagnosis_body = _AGENT_SERVICE.diagnose_ticket(ticket_text)
        
        # Validación obligatoria:
        if not diagnosis_body or diagnosis_body.strip() == "":
             raise RuntimeError("El modelo de IA devolvió un diagnóstico vacío.")
             
    except Exception as e:
        raise RuntimeError(f"Fallo al generar el diagnóstico: {e}")
            
    # 5. Actualizar ticket
    print(f"[Service] Enviando actualización a ticket {ticket_id}...")
    resp = actualizar_ticket(
        ticket_id=ticket_id,
        session_id=session_id,
        titulo=titulo,
        usuario=usuario,
        queue_id=queue_id,
        priority_id=priority_id,
        state_id=state_id,
        subject=subject,
        body=diagnosis_body, # Usamos el diagnóstico generado.
    )
    
    # 6. Manejar errores de actualización de Znuny
    if isinstance(resp, dict) and 'error' in resp:
        raise RuntimeError(f"Fallo al actualizar Znuny: {resp['error']}")

    return {
        "ok": True,
        "ticket_id": ticket_id,
        "diagnosis": diagnosis_body,
        "update_response": resp
    }