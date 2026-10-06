import os
import requests
from dotenv import load_dotenv

# Carga las variables del archivo .env
load_dotenv()

API_KEY = os.getenv("VONAGE_API_KEY")
API_SECRET = os.getenv("VONAGE_API_SECRET")
NUMERO_BOT = os.getenv("VONAGE_NUMERO_SANDBOX")
MI_NUMERO = os.getenv("MI_NUMERO")

URL_SANDBOX = "https://messages-sandbox.nexmo.com/v1/messages"

# Desde dónde, hacia quién, qué tipo de mensaje y por qué canal
datos = {
    "from": NUMERO_BOT,
    "to": MI_NUMERO,
    "message_type": "text",
    "text": "Hola Estudiantes Arrupe",
    "channel": "whatsapp",
}

# auth=(...) equivale a Client(account_sid, auth_token) de la guía
respuesta = requests.post(URL_SANDBOX, json=datos, auth=(API_KEY, API_SECRET))

print(respuesta.status_code)
print(respuesta.text)