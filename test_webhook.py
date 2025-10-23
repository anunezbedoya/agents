#!/usr/bin/env python3
"""Script para probar el webhook con un payload real de Znuny"""
import requests
import json

# Payload basado en el log real
payload = {
    "Data": {
        "Ticket": {
            "TicketID": 268,
            "TicketNumber": "2025100998000011",
            "Title": "Ticket night",
            "State": "new",
            "Priority": "3 normal",
            "Queue": "Raw"
        },
        "Event": {
            "TicketID": "268",
            "Event": "TicketCreate"
        }
    }
}

url = "http://127.0.0.1:5000/znuny-webhook"

print("Enviando webhook de prueba...")
print(json.dumps(payload, indent=2))

try:
    response = requests.post(url, json=payload, timeout=30)
    print(f"\nRespuesta: {response.status_code}")
    print(json.dumps(response.json(), indent=2))
except Exception as e:
    print(f"Error: {e}")
