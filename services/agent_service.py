# services/agent_service.py

from utils.adk_client import ADKClient
import json # Necesitamos la librería json para parsear
import os
import time
import requests


class AgentService:
    def __init__(self):
        self.adk_client = ADKClient()

    def diagnose_ticket(self, ticket_text: str) -> str:
        """
        Llama al modelo, recibe una cadena JSON, la parsea y retorna el texto
        de diagnóstico formateado para el artículo de Znuny.
        """
        json_string = self.adk_client.diagnose_ticket(ticket_text)
        
        if not json_string:
            return "Diagnóstico automático no disponible (Modelo de IA no respondió)."

        try:
            # Limpieza simple por si el modelo envuelve el JSON en bloques de código
            json_string = json_string.strip().lstrip('```json').rstrip('```').strip()
            
            # Parsear la cadena JSON
            diagnostico_data = json.loads(json_string)

            # Extraer los campos requeridos (tipo y diagnostico)
            tipo = diagnostico_data.get("tipo", "Sin Clasificar")
            diagnostico = diagnostico_data.get("diagnostico")
            
            if not diagnostico:
                 return f"Diagnóstico automático fallido: JSON de IA válido, pero falta la clave 'diagnostico'. JSON: {json_string}"

            # Formatear la salida final para el artículo de Znuny
            return f"[Clasificación: {tipo}]\n---\n{diagnostico}"
            
        except json.JSONDecodeError:
            # Si la salida no es JSON válido
            print(f"Error: La salida del modelo no fue JSON válida. Salida: {json_string}")
            return f"Error de Diagnóstico (Modelo): La respuesta de IA no fue JSON válida. Texto bruto: {json_string[:100]}..."
        except Exception as e:
            # Otros errores de parsing
            return f"Error inesperado al procesar diagnóstico: {e}"