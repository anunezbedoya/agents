import os
from dotenv import load_dotenv

# Cargar variables desde env_vars/.env (ruta relativa al proyecto)
load_dotenv("env_vars/.env")


def test_env_variables_present():
    """Verifica que las variables necesarias estén cargadas en el entorno."""
    assert os.environ.get("ZNUNY_BASE_API"), "ZNUNY_BASE_API no está definida"
    assert os.environ.get("ZNUNY_USERNAME"), "ZNUNY_USERNAME no está definida"
    assert os.environ.get("ZNUNY_PASSWORD"), "ZNUNY_PASSWORD no está definida"

    # Opcional: comprobar formato básico de la URL
    base = os.environ.get("ZNUNY_BASE_API")
    assert base.startswith("http"), "ZNUNY_BASE_API no parece una URL válida"