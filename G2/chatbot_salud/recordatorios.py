"""Revisa cada pocos segundos si toca enviar algún recordatorio.
Corre en un hilo aparte, en paralelo a Flask."""
import threading
import time
from datetime import date, datetime, timedelta

import datos
from canal import enviar_mensaje
from nlp import hora_legible, esta_despierto

SEGUNDOS_ENTRE_REVISIONES = 20
MINUTOS_PARA_REAVISO = 15     # si no responde, se le recuerda una vez más
MINUTOS_PARA_OMITIDA = 60     # si después de esto no respondió, la toma cuenta como omitida
HORA_AVISO_CITA = "19:00"     # el día anterior a la cita

FORMATO = "%Y-%m-%d %H:%M"


def texto_recordatorio(nombre, dosis, es_reaviso=False):
    inicio = "Te lo recuerdo de nuevo" if es_reaviso else "Es hora de tu medicina"
    return (f"💊 {inicio}: *{nombre}* ({dosis}).\n\n"
            "Respóndeme *tomé* cuando la tomes, o *posponer* si necesitas más tiempo "
            "(ej: _posponer 30 min_).")


def revisar(ahora):
    minuto = ahora.strftime(FORMATO)
    hora = ahora.strftime("%H:%M")

    # 1) Medicamentos que tocan en este minuto
    for med in datos.medicamentos_a_la_hora(hora):
        if datos.existe_toma(med["id"], minuto):
            continue  # ya se avisó en este minuto (evita mensajes duplicados)
        reaviso = (ahora + timedelta(minutes=MINUTOS_PARA_REAVISO)).strftime(FORMATO)
        datos.crear_toma(med, minuto, reaviso)
        enviar_mensaje(med["numero"], texto_recordatorio(med["nombre"], med["dosis"]))

    # 2) Re-avisos: no respondió a tiempo o pidió posponer
    for toma in datos.tomas_para_reavisar(minuto):
        datos.posponer_toma(toma["id"], None)  # solo se re-avisa una vez
        enviar_mensaje(toma["numero"], texto_recordatorio(toma["nombre"], toma["dosis"], es_reaviso=True))

    # 3) Tomas sin respuesta después de un tiempo -> omitidas (corazón negro)
    limite = (ahora - timedelta(minutes=MINUTOS_PARA_OMITIDA)).strftime(FORMATO)
    datos.marcar_omitidas(limite)

    # 4) Citas: se avisan el día anterior a las 7 p. m. (o al despertar si a esa hora ya duerme).
    #    Si la cita se registró muy tarde y no alcanzó el aviso, se avisa la misma mañana.
    hoy = ahora.date().isoformat()
    manana = (ahora.date() + timedelta(days=1)).isoformat()
    for fecha_cita in (manana, hoy):
        for cita in datos.citas_sin_recordar(fecha_cita):
            despertar, dormir = datos.obtener_horario(cita["numero"])
            if not esta_despierto(hora, despertar, dormir):
                continue  # no es urgente: no despertamos a nadie
            if fecha_cita == manana:
                hora_aviso = HORA_AVISO_CITA if esta_despierto(HORA_AVISO_CITA, despertar, dormir) else despertar
                if hora < hora_aviso:
                    continue
                cuando = "mañana"
            else:
                if hora >= cita["hora"]:
                    datos.marcar_cita_recordada(cita["id"])  # ya pasó, no tiene sentido avisar
                    continue
                cuando = "hoy"
            datos.marcar_cita_recordada(cita["id"])
            enviar_mensaje(cita["numero"],
                           f"📅 Recordatorio: {cuando} tienes tu cita de *{cita['motivo']}* "
                           f"a las {hora_legible(cita['hora'])}\n¡Que te vaya bien!")


def _bucle():
    ultimo_minuto = None
    while True:
        ahora = datetime.now()
        minuto = ahora.strftime(FORMATO)
        if minuto != ultimo_minuto:  # cada minuto se revisa una sola vez
            try:
                revisar(ahora)
            except Exception as error:
                # Un error aquí no debe detener los recordatorios futuros
                print(f"[ERROR recordatorios] {error}")
            ultimo_minuto = minuto
        time.sleep(SEGUNDOS_ENTRE_REVISIONES)


def iniciar():
    hilo = threading.Thread(target=_bucle, daemon=True)  # daemon: se cierra junto con Flask
    hilo.start()
    print("[Navi] Recordatorios activos.")