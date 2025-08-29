# utils/schemas.py
from pydantic import BaseModel

class TicketInput(BaseModel):
    ticket_text: str