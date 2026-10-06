import os
from flask import Flask, request

import datos
import recordatorios
from bot import procesar_mensaje
from canal import enviar_mensaje

app = Flask(__name__)


# Vonage llama a esta ruta cada vez que alguien le escribe al bot
@app.route("/inbound", methods=["POST"])
def inbound():
    datos_mensaje = request.get_json(silent=True) or {}
    numero = datos_mensaje.get("from")
    tipo = datos_mensaje.get("message_type")

    if not numero:
        return "", 200

    # Audios, imágenes, stickers, etc.
    if tipo != "text":
        enviar_mensaje(numero, "Por ahora solo entiendo mensajes de texto. ¿Me lo escribes?")
        return "", 200

    texto = datos_mensaje.get("text", "")
    print(f"[ENTRADA] {numero}: {texto}")

    try:
        respuesta = procesar_mensaje(numero, texto)
    except Exception as error:
        # Si algo falla en la lógica, el usuario recibe un mensaje claro y el servidor sigue vivo
        print(f"[ERROR bot] {error}")
        respuesta = "Tuve un problema procesando tu mensaje. Escribe *menu* para empezar de nuevo."

    enviar_mensaje(numero, respuesta)
    return "", 200


# Vonage avisa aquí el estado de los mensajes enviados (entregado, leído...)
@app.route("/status", methods=["POST"])
def status():
    return "", 200


if __name__ == "__main__":
    datos.inicializar()
    recordatorios.iniciar()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
    import os
from flask import Flask, request

import datos
import recordatorios
from bot import procesar_mensaje
from canal import enviar_mensaje

app = Flask(__name__)


# Vonage llama a esta ruta cada vez que alguien le escribe al bot
@app.route("/inbound", methods=["POST"])
def inbound():
    datos_mensaje = request.get_json(silent=True) or {}
    numero = datos_mensaje.get("from")
    tipo = datos_mensaje.get("message_type")

    if not numero:
        return "", 200

    # Audios, imágenes, stickers, etc.
    if tipo != "text":
        enviar_mensaje(numero, "Por ahora solo entiendo mensajes de texto. ¿Me lo escribes?")
        return "", 200

    texto = datos_mensaje.get("text", "")
    print(f"[ENTRADA] {numero}: {texto}")

    try:
        respuesta = procesar_mensaje(numero, texto)
    except Exception as error:
        # Si algo falla en la lógica, el usuario recibe un mensaje claro y el servidor sigue vivo
        print(f"[ERROR bot] {error}")
        respuesta = "Tuve un problema procesando tu mensaje. Escribe *menu* para empezar de nuevo."

    enviar_mensaje(numero, respuesta)
    return "", 200


# Vonage avisa aquí el estado de los mensajes enviados (entregado, leído...)
@app.route("/status", methods=["POST"])
def status():
    return "", 200


if __name__ == "__main__":
    datos.inicializar()
    recordatorios.iniciar()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
    