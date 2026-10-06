import os
import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("VONAGE_API_KEY")
API_SECRET = os.getenv("VONAGE_API_SECRET")
NUMERO_BOT = os.getenv("VONAGE_NUMERO_SANDBOX")

URL_SANDBOX = "https://messages-sandbox.nexmo.com/v1/messages"


def enviar_mensaje(numero, texto):
    """Envía un mensaje de WhatsApp a un número. Devuelve True si Vonage lo aceptó."""
    datos = {
        "from": NUMERO_BOT,
        "to": numero,
        "message_type": "text",
        "text": texto,
        "channel": "whatsapp",
    }
    respuesta = requests.post(URL_SANDBOX, json=datos, auth=(API_KEY, API_SECRET), timeout=10)

    if respuesta.status_code != 202:
        print(f"[ERROR] No se pudo enviar a {numero}: {respuesta.status_code} {respuesta.text}")
        return False
    return True