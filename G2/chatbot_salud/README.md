# Navi — Chatbot de recordatorios de salud por WhatsApp

Chatbot en Python integrado con WhatsApp que ayuda a recordar medicamentos y citas médicas.
Proyecto de **Diseño de Aplicaciones con Inteligencia Artificial** — Tercer Año de Bachillerato DS "C", Colegio Español Padre Arrupe, 2026.

> Navi es un apoyo para recordar tratamientos. No reemplaza la indicación de un médico.

## Funcionalidades

- Registrar medicamentos con una o varias horas, intervalos (`cada 8 horas`) u horas relativas (`en 2 horas`).
- Registrar citas médicas con fechas naturales (`el próximo lunes`, `en una semana`) y enlace a Google Calendar.
- Recordatorios automáticos, segundo aviso si no hay respuesta y opción de posponer (`posponer 30 min`).
- Seguimiento de adherencia: responder `tomé` suma un ❤️; las tomas omitidas cuentan como 🖤.
- Resumen antes de guardar, con corrección en lenguaje natural (`no, la hora es 9pm`).
- Editar y eliminar recordatorios (uno o varios).
- Horario de sueño: los intervalos empiezan al despertar y los avisos no urgentes no llegan de noche.
- Detección de emergencias con 911, contacto de emergencia y hospitales cercanos.
- Búsqueda de farmacias, hospitales y clínicas cercanas con Google Maps.
- Privacidad: `borrar mis datos` elimina toda la información del usuario.

## Tecnologías

Python 3.12 · Flask · SQLite · Vonage Messages API (sandbox de WhatsApp) · Cloudflare Tunnel

## Estructura

```
app.py              Servidor Flask: recibe mensajes de Vonage (webhook)
canal.py            Envío de mensajes por la API de Vonage
bot.py              Lógica de conversación: estados, flujos y respuestas
nlp.py              Procesamiento de lenguaje: intenciones y entidades (horas, fechas)
datos.py            Base de datos SQLite
recordatorios.py    Hilo que revisa y envía los recordatorios
probar_terminal.py  Prueba del bot en consola, sin WhatsApp
```

## Instalación

```bash
python -m venv venv
.\venv\Scripts\Activate.ps1        # Windows PowerShell
pip install -r requirements.txt
```

Crea un archivo `.env` en la raíz:

```
VONAGE_API_KEY=tu_api_key
VONAGE_API_SECRET=tu_api_secret
VONAGE_NUMERO_SANDBOX=14157386102
MI_NUMERO=503XXXXXXXX
```

## Ejecución

1. Probar la lógica sin WhatsApp: `python probar_terminal.py`
2. Iniciar el servidor: `python app.py`
3. En otra terminal, exponerlo: `cloudflared tunnel --url http://localhost:5000`
4. En el dashboard de Vonage → Messaging → Sandbox → Webhooks:
   - Inbound: `https://<tu-url>.trycloudflare.com/inbound`
   - Status: `https://<tu-url>.trycloudflare.com/status`
5. Escribe `hola` al número del sandbox desde WhatsApp.

> La URL de Cloudflare cambia cada vez que se reinicia el túnel: actualiza los webhooks cuando eso pase.

## Limitaciones conocidas

- Chatbot basado en reglas (procesamiento de lenguaje clásico, sin aprendizaje automático).
- El sandbox solo funciona con números aprobados y dentro de la ventana de 24 horas de WhatsApp.
- Requiere que el servidor esté encendido para enviar recordatorios.
- Las conversaciones a medias se pierden al reiniciar el servidor (los datos guardados no).
- Los webhooks no verifican la firma de Vonage (mejora futura).