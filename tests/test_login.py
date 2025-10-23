import json
from types import SimpleNamespace
import services.update_service as update_service

class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {"SessionID": "fake-session-123"}
        self.text = json.dumps(self._payload)

    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception("HTTP error")

    def json(self):
        return self._payload


def fake_patch(url, data=None, headers=None, timeout=None):
    # Devuelve una respuesta simulada con SessionID
    return FakeResponse(status_code=200, payload={"SessionID": "fake-session-123"})


def test_login_create_session_monkeypatch(monkeypatch, tmp_path):
    """Parchea requests.patch en el módulo para simular login y comprobar el SessionID."""
    # Asegurarse de que las variables de entorno necesarias existan (se usan por la función)
    import os
    os.environ.setdefault("ZNUNY_BASE_API", "http://localhost/otrs")
    os.environ.setdefault("ZNUNY_USERNAME", "rvargas")
    os.environ.setdefault("ZNUNY_PASSWORD", "nexura2025")

    # Parchear la llamada a requests.patch dentro del módulo update_service
    monkeypatch.setattr(update_service.requests, "patch", fake_patch)

    session_id = update_service._login_create_session()

    assert session_id == "fake-session-123"
