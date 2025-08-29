from google import genai
from google.genai import types
import os

class ADKClient:
    def __init__(self):
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("La variable de entorno GOOGLE_API_KEY no está configurada.")
        self.client = genai.Client(api_key=api_key)

    

    def diagnose_ticket(self, ticket_text: str) -> str:
        try:
            response = self.client.models.generate_content(
                model="gemini-2.5-flash",       # Ajusta según el modelo disponible
                contents=ticket_text,
                config=types.GenerateContentConfig(
                    thinking_config=types.ThinkingConfig(thinking_budget=0)
                )
            )
            return response.text

        except Exception as e:
            print(f"❌ Error en diagnose_ticket: {e}")
            return ""