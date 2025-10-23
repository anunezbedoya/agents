import os
import time
import json
import requests

# Cache de sesión
_CACHED_SESSION_ID = None
_CACHED_SESSION_TS = 0.0
_SESSION_TTL_SECONDS = int(os.environ.get("ZNUNY_SESSION_TTL", "3300"))  # ~55 min por defecto


def _znuny_api_base() -> str:
    """Devuelve la base URL de la API REST de Znuny/OTRS."""
    return os.environ.get(
        "ZNUNY_BASE_API",
        "http://localhost:8080/otrs/nph-genericinterface.pl/Webservice/GenericTicketConnectorREST"
    ).rstrip("/")


def _login_create_session() -> str:
    """Crea un nuevo SessionID autenticando contra Znuny."""
    user = os.environ.get("ZNUNY_USER", "root@localhost")
    password = os.environ.get("ZNUNY_PASS", "NVhPcVbpyytIDMeS")

    if not user or not password:
        raise RuntimeError("Faltan ZNUNY_USER y/o ZNUNY_PASS en variables de entorno")

    url = f"{_znuny_api_base()}/Session"
    # Use the local `password` variable as the credential sent to Znuny
    payload = {"UserLogin": user, "Password": password}
    headers = {
        "Content-Type": "application/json; charset=UTF-8",
        "Accept": "application/json",
        "Accept-Encoding": "identity",
        "User-Agent": "curl/7.81.0",
    }

    print(f"[Znuny] Intentando autenticación PATCH en {url}")
    print(f"[Znuny] Payload: {json.dumps(payload)}")

    try:
        resp = requests.patch(
            url,
            data=json.dumps(payload),
            headers=headers,
            timeout=10
        )
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Error de conexión al autenticar: {e}")

    print(f"[Znuny] Status: {resp.status_code}")
    print(f"[Znuny] Respuesta: {resp.text}")

    resp.raise_for_status()
    data = resp.json()

    session_id = (
        data.get("SessionID")
        or data.get("Session")
        or data.get("session_id")
    )

    if not session_id:
        raise RuntimeError(f"Znuny no devolvió SessionID. Respuesta: {data}")

    print(f"[Znuny] ✅ Login exitoso. SessionID: {session_id[:10]}...")
    return session_id


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


def get_ticket_latest_article(ticket_id: int, session_id: str) -> str | None:
    """Obtiene el texto del último artículo de un ticket en Znuny."""
    def _extract_body(articles):
        if not isinstance(articles, list) or not articles:
            return None
        last = sorted(
            articles,
            key=lambda a: a.get("CreateTime") or a.get("ArticleID") or 0
        )[-1]
        return (
            last.get("Body") or last.get("body")
            or last.get("Content") or last.get("content")
            or last.get("Text") or last.get("text")
        )

    base = _znuny_api_base()
    headers = {"Accept": "application/json"}

    # Intentar con Ticket/{id}?AllArticles=1
    try:
        url_ticket = f"{base}/Ticket/{ticket_id}?SessionID={session_id}&AllArticles=1"
        r = requests.get(url_ticket, headers=headers, timeout=10)
        if r.status_code == 200:
            data = r.json()
            ticket_data = data.get("Ticket")
            if isinstance(ticket_data, list):
                ticket_data = ticket_data[0]
            articles = (
                ticket_data.get("Article") or ticket_data.get("Articles")
                or ticket_data.get("article") or ticket_data.get("articles")
                if ticket_data else None
            )
            body = _extract_body(articles)
            if body:
                return body
    except Exception:
        pass

    # Fallback con Article?TicketID=...
    try:
        url_article = f"{base}/Article?TicketID={ticket_id}&SessionID={session_id}"
        r2 = requests.get(url_article, headers=headers, timeout=10)
        if r2.status_code == 200:
            data2 = r2.json()
            articles2 = (
                data2.get("Article") or data2.get("Articles")
                or data2.get("article") or data2.get("articles")
            )
            return _extract_body(articles2)
    except Exception:
        pass

    return None


def actualizar_ticket(ticket_id, session_id, titulo, usuario, queue_id, priority_id, state_id, subject, body, dynamic_fields=None):
    """Actualiza un ticket en Znuny agregando un nuevo artículo."""
    url = f"{_znuny_api_base()}/Ticket/{ticket_id}"
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
        return {"error": str(e)}
