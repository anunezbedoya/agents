import os
import pytest
from dotenv import load_dotenv

# Cargar variables desde env_vars/.env
load_dotenv("env_vars/.env")

RUN_INTEGRATION = os.environ.get("RUN_INTEGRATION_TESTS", "0") in ("1", "true", "True")

@pytest.mark.skipif(not RUN_INTEGRATION, reason="Integration tests disabled. Set RUN_INTEGRATION_TESTS=1 to enable.")
def test_login_integration():
    """Prueba de integración: intenta autenticar contra la API real de Znuny y devuelve SessionID.

    Esta prueba hace una petición real a la URL indicada en ZNUNY_BASE_API usando
    ZNUNY_USERNAME y ZNUNY_PASSWORD del archivo `env_vars/.env` (si lo tienes).

    IMPORTANTE: Activar ejecutando pytest con la variable de entorno RUN_INTEGRATION_TESTS=1.
    """
    # Verificar que las variables necesarias están presentes
    assert os.environ.get("ZNUNY_BASE_API"), "ZNUNY_BASE_API no está definida"
    assert os.environ.get("ZNUNY_USERNAME"), "ZNUNY_USERNAME no está definida"
    assert os.environ.get("ZNUNY_PASSWORD"), "ZNUNY_PASSWORD no está definida"

    # Importar el módulo bajo prueba
    import services.update_service as update_service

    # Llamar a la función que hace login real
    session_id = update_service._login_create_session()

    # Comprobaciones mínimas
    assert session_id is not None
    assert isinstance(session_id, str)
    assert len(session_id) > 0
