#!/usr/bin/env python3
"""Script para probar el flujo completo del webhook sin iniciar Flask"""
import sys
import os
import json

# Configurar el SessionID
os.environ['ZNUNY_SESSION_ID'] = 'mErW7bSnyoKluqLURZRlqtfsvnl7pPiv'

sys.path.insert(0, '/home/usuario/Documentos/agents/agents')

from services.update_service import get_or_create_session_id, get_ticket_latest_article

# Simular el payload del webhook
payload = {
    "Ticket": {
        "TicketID": 269,
        "TicketNumber": "2025100998000011",
        "Title": "Ticket night"
    },
    "Event": {
        "TicketID": "269",
        "Event": "TicketCreate"
    }
}

print("=" * 60)
print("PRUEBA DEL FLUJO COMPLETO DEL WEBHOOK")
print("=" * 60)

# 1. Extraer TicketID
ticket_id = (
    payload.get("TicketID")
    or payload.get("ticket_id")
    or (payload.get("Ticket") or {}).get("TicketID")
    or (payload.get("Data") or {}).get("Event", {}).get("TicketID")
    or (payload.get("Event") or {}).get("TicketID")
)

print(f"\n1. ✅ TicketID extraído: {ticket_id}")

# 2. Obtener SessionID
try:
    session_id = get_or_create_session_id()
    print(f"2. ✅ SessionID obtenido: {session_id[:20]}...")
except Exception as e:
    print(f"2. ❌ Error obteniendo SessionID: {e}")
    sys.exit(1)

# 3. Obtener el último artículo del ticket
print(f"\n3. Obteniendo último artículo del ticket {ticket_id}...")
try:
    ticket_text = get_ticket_latest_article(ticket_id, session_id)
    if ticket_text:
        print(f"   ✅ Artículo obtenido ({len(ticket_text)} caracteres)")
        print(f"   Primeros 100 caracteres: {ticket_text[:100]}")
    else:
        print("   ⚠️  No se encontró artículo (puede ser normal si el ticket está vacío)")
except Exception as e:
    print(f"   ❌ Error: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)
print("RESUMEN:")
print(f"  - TicketID: {ticket_id}")
print(f"  - SessionID: {'✅ OK' if session_id else '❌ FALLO'}")
print(f"  - Artículo: {'✅ OK' if ticket_text else '⚠️  Vacío'}")
print("=" * 60)
