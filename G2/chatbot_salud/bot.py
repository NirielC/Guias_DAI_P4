"""Cerebro de Navi: recibe (numero, texto) y devuelve el texto de respuesta.
No sabe nada de WhatsApp ni de Vonage: por eso se puede probar en la terminal."""
import re
from datetime import date, datetime, timedelta

import datos
from nlp import (normalizar, contiene, detectar_intencion, es_emergencia, es_si, es_no,
                 extraer_horas, extraer_hora_relativa, extraer_minutos_relativos, extraer_intervalo,
                 generar_horas_periodicas, esta_despierto, hora_legible, horas_legibles,
                 extraer_fecha, fecha_legible, extraer_campos, enlace_calendario, enlace_mapa)

MINUTOS_POSPONER = 10
INTERVALOS_VALIDOS = (2, 3, 4, 6, 8, 12, 24)  # los que cuadran exacto en el día

# Palabras que el usuario puede usar para decir qué dato cambiar
ETIQUETAS_MED = {"nombre": ["nombre", "medicamento", "medicina"],
                 "dosis": ["dosis", "cantidad"],
                 "horas": ["hora", "horas", "horario"]}
ETIQUETAS_CITA = {"motivo": ["motivo", "razon", "especialidad"],
                  "fecha": ["fecha", "dia"],
                  "hora": ["hora"]}

LUGARES = {"farmacia": "farmacias", "hospital": "hospitales", "clinica": "clínicas",
           "unidad de salud": "unidades de salud", "laboratorio": "laboratorios clínicos"}

# Estado de la conversación de cada usuario. Vive en memoria: si el servidor se reinicia,
# se pierde la conversación a medias, pero NO los datos guardados (esos están en SQLite).
sesiones = {}


# ======================================================================
# Textos
# ======================================================================

def texto_menu():
    return (
        "Hola, soy *Navi* 👋 Te ayudo a recordar tus medicinas y tus citas médicas.\n\n"
        "💊 *Medicamentos*\n"
        "1. Registrar un medicamento\n"
        "2. Ver mis medicamentos\n\n"
        "📅 *Citas*\n"
        "3. Registrar una cita\n"
        "4. Ver mis citas\n\n"
        "⚙️ *Más opciones*\n"
        "5. Editar\n"
        "6. Eliminar\n"
        "7. Mi perfil (horario y contacto de emergencia)\n"
        "8. Buscar farmacias u hospitales cercanos\n\n"
        "Escribe el número o dime con tus palabras qué necesitas.\n\n"
        "_Soy un apoyo, no reemplazo a tu médico._"
    )


TEXTO_AYUDA = (
    "💡 *Así funciono:*\n\n"
    "• Escribe un número del menú o dímelo normal: _\"quiero registrar una pastilla\"_.\n"
    "• Horas: _8 am_, _8am y 8pm_, _cada 8 horas_ o _en 2 horas_.\n"
    "• Fechas: _15/10_, _mañana_, _el próximo lunes_, _en una semana_.\n"
    "• Antes de guardar te muestro un resumen: responde *sí*, *no*, o dime qué cambiar (_hora 9pm_).\n"
    "• Cuando te recuerde una medicina, responde *tomé* o *posponer* (o _posponer 30 min_).\n"
    "• *menu* te regresa al inicio y *cancelar* detiene lo que estemos haciendo.\n"
    "• *borrar mis datos* elimina toda tu información.\n\n"
    "¿Qué te gustaría hacer?"
)

TEXTO_DESPEDIDA = "¡Cuídate mucho! 💚 Aquí estaré para recordarte tus medicinas. Escribe *hola* cuando me necesites."


def texto_emergencia(numero):
    perfil = datos.obtener_perfil(numero)
    partes = ["🚨 Lo que me cuentas podría ser una *emergencia*.\n",
              "Yo no puedo ayudarte con esto, pero por favor no esperes:",
              "📞 Llama al *911*"]
    if perfil["contacto_numero"]:
        partes.append(f"📞 Tu contacto de emergencia, *{perfil['contacto_nombre']}*: "
                      f"{telefono_legible(perfil['contacto_numero'])}")
    partes.append(f"\n🏥 Hospitales cercanos:\n{enlace_mapa('hospitales')}")
    if not perfil["contacto_numero"]:
        partes.append("\n_Consejo: guarda un contacto de emergencia en *Mi perfil* (opción 7)._")
    return "\n".join(partes)


def telefono_legible(digitos):
    if digitos.startswith("503") and len(digitos) == 11:
        return f"+503 {digitos[3:7]} {digitos[7:]}"
    return f"+{digitos}"


# ======================================================================
# Sesiones
# ======================================================================

def obtener_sesion(numero):
    if numero not in sesiones:
        sesiones[numero] = {"estado": "MENU", "temp": {}, "fallos": 0}
    return sesiones[numero]


def reiniciar(sesion):
    sesion["estado"] = "MENU"
    sesion["temp"] = {}
    sesion["fallos"] = 0


# ======================================================================
# Punto de entrada
# ======================================================================

def procesar_mensaje(numero, texto):
    sesion = obtener_sesion(numero)
    t = normalizar(texto)

    if not t:
        return "No logré leer tu mensaje. ¿Me lo escribes de nuevo?"

    # 1) Prioridad máxima: emergencias, en cualquier momento
    if es_emergencia(t):
        reiniciar(sesion)
        return texto_emergencia(numero)

    # 2) Comandos globales: siempre funcionan
    if t in ("menu", "inicio", "cancelar") or t.startswith("cancelar"):
        estaba_ocupado = sesion["estado"] != "MENU"
        reiniciar(sesion)
        prefijo = "Listo, cancelé lo que estábamos haciendo.\n\n" if estaba_ocupado else ""
        return prefijo + texto_menu()

    # 3) Respuesta a un recordatorio ("tomé" / "posponer"), aunque esté a mitad de otro flujo
    exacta = detectar_intencion(t, aproximado=False)
    if exacta in ("confirmar_toma", "posponer") and datos.toma_pendiente(numero):
        respuesta = responder_toma(numero, exacta, texto)
        if sesion["estado"] != "MENU":
            respuesta += "\n\n_Seguimos con lo que estábamos haciendo._"
        return respuesta

    # 4) Si está a mitad de un flujo, el estado manda
    if sesion["estado"] != "MENU":
        return manejar_estado(numero, sesion, texto, t)

    # 5) Si no, actuamos según la intención
    return manejar_intencion(numero, sesion, detectar_intencion(t), t)


def manejar_intencion(numero, sesion, intencion, t):
    if intencion is None:
        sesion["fallos"] += 1
        if sesion["fallos"] >= 2:
            sesion["fallos"] = 0
            return "Creo que no te estoy entendiendo bien 😅 Te muestro las opciones:\n\n" + texto_menu()
        return ("Mmm, no estoy segura de qué necesitas 🤔\n"
                "Puedes escribir un número del *1* al *8*, algo como _\"registrar medicina\"_, "
                "o *ayuda* para ver ejemplos.")
    sesion["fallos"] = 0

    if intencion == "menu":
        return texto_menu()
    if intencion == "ayuda":
        return TEXTO_AYUDA
    if intencion == "despedida":
        return TEXTO_DESPEDIDA
    if intencion in ("confirmar_toma", "posponer"):
        return "No tienes ninguna medicina pendiente ahorita 👍 Te aviso cuando sea la hora."

    if intencion == "registrar_medicamento":
        sesion["estado"] = "MED_NOMBRE"
        return "💊 ¡Vamos a registrarlo! ¿Cómo se llama el medicamento?"
    if intencion == "registrar_cita":
        sesion["estado"] = "CITA_MOTIVO"
        return "📅 ¡Perfecto! ¿Con quién o para qué es la cita? (ej: _medicina general_, _dentista_)"

    if intencion == "ver_medicamentos":
        return texto_medicamentos(numero)
    if intencion == "ver_citas":
        return texto_citas(numero)
    if intencion == "ver":
        return texto_medicamentos(numero) + "\n\n" + texto_citas(numero)

    if intencion in ("editar", "eliminar"):
        filtro = "cita" if "cita" in t else ("med" if re.search(r"medic|pastill|remedio", t) else None)
        return iniciar_seleccion(numero, sesion, intencion, filtro)

    if intencion == "perfil":
        if "contacto" in t:
            sesion["estado"] = "CONTACTO_NOMBRE"
            return "📞 ¿Cómo se llama tu contacto de emergencia? (ej: _Mamá_)"
        if re.search(r"horario|dormir|duermo|despertar|levanto", t):
            return iniciar_horario(sesion)
        return texto_perfil(numero, sesion)

    if intencion == "buscar_lugar":
        lugar = detectar_lugar(t)
        if lugar:
            return f"📍 Aquí tienes {lugar} cerca de ti:\n{enlace_mapa(lugar)}"
        sesion["estado"] = "BUSCAR_ELEGIR"
        return ("📍 ¿Qué quieres buscar cerca de ti?\n\n"
                "1. Farmacias\n2. Hospitales\n3. Clínicas\n4. Unidades de salud")

    if intencion == "borrar_datos":
        sesion["estado"] = "BORRAR_CONFIRMAR"
        return ("⚠️ Esto eliminará *todos* tus medicamentos, citas, historial y perfil, "
                "y no se puede deshacer.\n¿Estás seguro? Responde *sí* o *no*.")

    return texto_menu()


# ======================================================================
# Recordatorios: "tomé" / "posponer"
# ======================================================================

def responder_toma(numero, intencion, texto):
    toma = datos.toma_pendiente(numero)
    if intencion == "posponer":
        minutos = extraer_minutos_relativos(texto) or MINUTOS_POSPONER
        minutos = max(5, min(minutos, 180))
        nuevo = (datetime.now() + timedelta(minutes=minutos)).strftime("%Y-%m-%d %H:%M")
        datos.posponer_toma(toma["id"], nuevo)
        return f"⏰ Va, te recuerdo *{toma['nombre']}* en {minutos} minutos."
    datos.marcar_toma(toma["id"], "tomada")
    return f"✅ ¡Bien hecho! Registré tu toma de *{toma['nombre']}*.\n\n{texto_corazones(numero)}"


def texto_corazones(numero):
    tomas = datos.ultimas_tomas(numero)
    if not tomas:
        return ""
    corazones = "".join("❤️" if t["estado"] == "tomada" else "🖤" for t in tomas)
    tomadas = sum(1 for t in tomas if t["estado"] == "tomada")
    return f"Tus últimas tomas: {corazones}\n({tomadas} de {len(tomas)} cumplidas)"


# ======================================================================
# Flujos por estado
# ======================================================================

def manejar_estado(numero, sesion, texto, t):
    estado = sesion["estado"]
    temp = sesion["temp"]

    # ---------- Registrar medicamento ----------
    if estado == "MED_NOMBRE":
        nombre, error = validar_nombre(texto)
        if error:
            return error
        existente = datos.buscar_medicamento_por_nombre(numero, nombre)
        if existente:
            reiniciar(sesion)
            return (f"Ya tienes *{existente['nombre']}* registrado ({horas_legibles(existente['horas'])}).\n"
                    "Si quieres cambiarle algo, escribe *editar*.")
        temp["med"] = {"nombre": nombre}
        sesion["estado"] = "MED_DOSIS"
        return f"Anotado: *{nombre}*. ¿Qué dosis tomas? (ej: _1 pastilla_, _500 mg_, _10 ml_)"

    if estado == "MED_DOSIS":
        dosis, error = validar_dosis(texto)
        if error:
            return error
        temp["med"]["dosis"] = dosis
        sesion["estado"] = "MED_HORA"
        return ("⏰ ¿A qué hora debo recordártelo?\n"
                "Puede ser una o varias (_8 am_, _8am y 8pm_), un intervalo (_cada 8 horas_) "
                "o _en 2 horas_.")

    if estado == "MED_HORA":
        horas, error = interpretar_horas_medicamento(numero, texto)
        if error:
            return error
        temp["med"]["horas"] = horas
        sesion["estado"] = "MED_CONFIRMAR"
        return resumen_medicamento(numero, temp["med"], "Revisemos")

    # ---------- Registrar cita ----------
    if estado == "CITA_MOTIVO":
        motivo, error = validar_motivo(texto)
        if error:
            return error
        temp["cita"] = {"motivo": motivo}
        sesion["estado"] = "CITA_FECHA"
        return "📅 ¿Qué día es? (ej: _15/10_, _mañana_, _el próximo lunes_). Si quieres, incluye la hora."

    if estado == "CITA_FECHA":
        fecha, hora, error = interpretar_fecha_y_hora(texto)
        if error:
            return error
        temp["cita"]["fecha"] = fecha
        if hora:  # dijo fecha y hora juntas: nos saltamos un paso
            error = validar_momento_cita(fecha, hora)
            if error:
                return error
            temp["cita"]["hora"] = hora
            sesion["estado"] = "CITA_CONFIRMAR"
            return resumen_cita(temp["cita"], "Revisemos")
        sesion["estado"] = "CITA_HORA"
        return "⏰ ¿A qué hora es la cita? (ej: _9:30 am_)"

    if estado == "CITA_HORA":
        hora, error = interpretar_una_hora(texto)
        if error:
            return error
        error = validar_momento_cita(temp["cita"]["fecha"], hora)
        if error:
            return error
        temp["cita"]["hora"] = hora
        sesion["estado"] = "CITA_CONFIRMAR"
        return resumen_cita(temp["cita"], "Revisemos")

    # ---------- Confirmaciones (registro y edición usan las mismas) ----------
    if estado in ("MED_CONFIRMAR", "CITA_CONFIRMAR"):
        return manejar_confirmacion(numero, sesion, texto, t)

    # ---------- Editar ----------
    if estado == "EDITAR_ELEGIR":
        m = re.match(r"\s*(\d+)\s*[.,:-]?\s*(.*)", texto)
        opcion = elegir_una(temp["opciones"], m.group(1)) if m else None
        if opcion is None:
            return f"Escríbeme solo el número (del 1 al {len(temp['opciones'])}), o *cancelar*."
        cargar_para_editar(numero, sesion, opcion)
        if m.group(2).strip():  # "2 hora 9pm": eligió y dijo el cambio en el mismo mensaje
            return manejar_confirmacion(numero, sesion, m.group(2), normalizar(m.group(2)))
        return pedir_cambios(numero, sesion)

    # ---------- Eliminar ----------
    if estado == "ELIMINAR_ELEGIR":
        elegidas = elegir_varias(temp["opciones"], t)
        if not elegidas:
            return (f"Escríbeme el número o varios (ej: _1_, _1 y 3_, _todos_), "
                    f"del 1 al {len(temp['opciones'])}. O *cancelar*.")
        temp["elegidas"] = elegidas
        sesion["estado"] = "ELIMINAR_CONFIRMAR"
        lista = "\n".join(f"• {o['descripcion']}" for o in elegidas)
        return f"🗑️ Voy a eliminar:\n{lista}\n\n¿Confirmas? Responde *sí* o *no*."

    if estado == "ELIMINAR_CONFIRMAR":
        if es_si(t):
            for o in temp["elegidas"]:
                if o["tipo"] == "med":
                    datos.eliminar_medicamento(numero, o["id"])
                else:
                    datos.eliminar_cita(numero, o["id"])
            cantidad = len(temp["elegidas"])
            reiniciar(sesion)
            return f"✅ Listo, eliminé {cantidad} {'recordatorio' if cantidad == 1 else 'recordatorios'}."
        if es_no(t):
            reiniciar(sesion)
            return "No eliminé nada 👍 Escribe *menu* para ver opciones."
        return "Responde *sí* para eliminar o *no* para cancelar."

    # ---------- Perfil ----------
    if estado == "PERFIL_ELEGIR":
        if t == "1" or re.search(r"horario|dormir|despertar", t):
            return iniciar_horario(sesion)
        if t == "2" or "contacto" in t:
            sesion["estado"] = "CONTACTO_NOMBRE"
            return "📞 ¿Cómo se llama tu contacto de emergencia? (ej: _Mamá_)"
        return "Escribe *1* para tu horario o *2* para tu contacto de emergencia."

    if estado == "HORARIO_DESPERTAR":
        hora, error = interpretar_una_hora(texto)
        if error:
            return error
        temp["despertar"] = hora
        sesion["estado"] = "HORARIO_DORMIR"
        return "🌙 ¿Y a qué hora te duermes normalmente? (ej: _10 pm_)"

    if estado == "HORARIO_DORMIR":
        hora, error = interpretar_una_hora(texto)
        if error:
            return error
        if hora == temp["despertar"]:
            return "La hora de dormir no puede ser igual a la de levantarte. ¿A qué hora te duermes?"
        temp["dormir"] = hora
        sesion["estado"] = "HORARIO_CONFIRMAR"
        return (f"Revisemos:\n☀️ Te levantas: {hora_legible(temp['despertar'])}\n"
                f"🌙 Te duermes: {hora_legible(hora)}\n\n¿Lo guardo? Responde *sí* o *no*.")

    if estado == "HORARIO_CONFIRMAR":
        if es_si(t):
            datos.guardar_horario(numero, temp["despertar"], temp["dormir"])
            reiniciar(sesion)
            return ("✅ ¡Guardado! Usaré tu horario para que las tomas de \"cada X horas\" empiecen "
                    "al levantarte, y para no enviarte avisos que no son urgentes mientras duermes.")
        if es_no(t):
            reiniciar(sesion)
            return "No guardé cambios 👍 Escribe *7* si quieres intentarlo de nuevo."
        return "Responde *sí* para guardar o *no* para cancelar."

    if estado == "CONTACTO_NOMBRE":
        nombre = texto.strip()
        if not 2 <= len(nombre) <= 30:
            return "Escríbeme un nombre corto, por ejemplo: _Mamá_ o _Carlos_."
        temp["contacto_nombre"] = nombre
        sesion["estado"] = "CONTACTO_NUMERO"
        return f"¿Cuál es el número de *{nombre}*? (ej: _7123 4567_)"

    if estado == "CONTACTO_NUMERO":
        digitos = re.sub(r"\D", "", texto)
        if len(digitos) == 8:  # número salvadoreño sin código de país
            digitos = "503" + digitos
        if not 10 <= len(digitos) <= 15:
            return "Ese número no parece válido. Escríbelo así: _7123 4567_ o _+503 7123 4567_."
        temp["contacto_numero"] = digitos
        sesion["estado"] = "CONTACTO_CONFIRMAR"
        return (f"Revisemos:\n📞 *{temp['contacto_nombre']}*: {telefono_legible(digitos)}\n\n"
                "¿Lo guardo? Responde *sí* o *no*.")

    if estado == "CONTACTO_CONFIRMAR":
        if es_si(t):
            datos.guardar_contacto(numero, temp["contacto_nombre"], temp["contacto_numero"])
            reiniciar(sesion)
            return "✅ ¡Guardado! Si alguna vez me cuentas una emergencia, te mostraré este contacto."
        if es_no(t):
            reiniciar(sesion)
            return "No guardé el contacto 👍 Escribe *7* si quieres intentarlo de nuevo."
        return "Responde *sí* para guardar o *no* para cancelar."

    # ---------- Buscar lugares ----------
    if estado == "BUSCAR_ELEGIR":
        opciones = {"1": "farmacias", "2": "hospitales", "3": "clínicas", "4": "unidades de salud"}
        lugar = opciones.get(t) or detectar_lugar(t)
        if not lugar:
            return "Escribe un número del *1* al *4*, o *cancelar*."
        reiniciar(sesion)
        return f"📍 Aquí tienes {lugar} cerca de ti:\n{enlace_mapa(lugar)}"

    # ---------- Borrar todos los datos ----------
    if estado == "BORRAR_CONFIRMAR":
        if es_si(t):
            datos.borrar_datos_usuario(numero)
            reiniciar(sesion)
            return "🧹 Listo, eliminé toda tu información. Si vuelves a escribirme, empezamos de cero."
        if es_no(t):
            reiniciar(sesion)
            return "No borré nada 😌 Escribe *menu* para ver opciones."
        return "Responde *sí* para borrar todo o *no* para cancelar."

    # Estado desconocido (no debería pasar): volvemos al inicio sin romper nada
    reiniciar(sesion)
    return texto_menu()


# ======================================================================
# Confirmar: sí / no / "cambia la hora a 9pm"
# ======================================================================

def manejar_confirmacion(numero, sesion, texto, t):
    es_med = sesion["estado"] == "MED_CONFIRMAR"
    temp = sesion["temp"]

    # 1) ¿Pidió cambios? (va primero para que "no, la hora es 9pm" se entienda como corrección)
    if es_med:
        cambios, error = aplicar_cambios_medicamento(numero, temp["med"], texto)
    else:
        cambios, error = aplicar_cambios_cita(temp["cita"], texto)
    if error:
        return error
    if cambios:
        if es_med:
            return resumen_medicamento(numero, temp["med"], "Así quedaría")
        return resumen_cita(temp["cita"], "Así quedaría")

    # 2) Sí: guardar
    if es_si(t):
        return guardar_medicamento(numero, sesion) if es_med else guardar_cita(numero, sesion)

    # 3) No: cancelar
    if es_no(t):
        reiniciar(sesion)
        return "Sin problema, no guardé nada 👍 Escribe *menu* para ver opciones."

    # 4) Ninguna de las anteriores
    ejemplo = "_hora 9pm_ o _dosis 2 pastillas_" if es_med else "_hora 10am_ o _fecha el lunes_"
    return f"Responde *sí* para guardar, *no* para cancelar, o dime qué cambiar (ej: {ejemplo})."


def guardar_medicamento(numero, sesion):
    med = sesion["temp"]["med"]
    otro = datos.buscar_medicamento_por_nombre(numero, med["nombre"])
    if otro and otro["id"] != med.get("id"):
        return f"Ya tienes otro medicamento llamado *{otro['nombre']}*. Cambia el nombre (ej: _nombre {med['nombre']} 2_) o escribe *cancelar*."

    if med.get("id"):
        ok = datos.actualizar_medicamento(numero, med["id"], med["nombre"], med["dosis"], med["horas"])
        reiniciar(sesion)
        return "✅ ¡Cambios guardados!" if ok else "No encontré ese medicamento, quizá ya fue eliminado."

    datos.agregar_medicamento(numero, med["nombre"], med["dosis"], med["horas"])
    reiniciar(sesion)
    return (f"✅ ¡Listo! Te avisaré cuando sea hora de tomar *{med['nombre']}*.\n"
            "Cuando te llegue el recordatorio, respóndeme *tomé* y sumas un ❤️.")


def guardar_cita(numero, sesion):
    cita = sesion["temp"]["cita"]
    if cita.get("id"):
        ok = datos.actualizar_cita(numero, cita["id"], cita["motivo"], cita["fecha"].isoformat(), cita["hora"])
        reiniciar(sesion)
        return "✅ ¡Cambios guardados!" if ok else "No encontré esa cita, quizá ya fue eliminada."

    datos.agregar_cita(numero, cita["motivo"], cita["fecha"].isoformat(), cita["hora"])
    enlace = enlace_calendario(cita["motivo"], cita["fecha"], cita["hora"])
    reiniciar(sesion)
    return ("✅ ¡Cita guardada! Te la recordaré el día anterior.\n\n"
            f"📲 Si quieres tenerla también en tu calendario, toca aquí:\n{enlace}")


# ======================================================================
# Validar e interpretar datos
# ======================================================================

def validar_nombre(texto):
    nombre = texto.strip(" .,")
    if len(nombre) < 2 or len(nombre) > 50 or nombre.isdigit():
        return None, "Ese nombre no parece válido. Escríbeme el nombre del medicamento, por ejemplo: _Paracetamol_."
    return nombre[0].upper() + nombre[1:], None


def validar_dosis(texto):
    dosis = texto.strip(" .,")
    if not dosis or len(dosis) > 50:
        return None, "Escríbeme la dosis de forma corta, por ejemplo: _1 pastilla_ o _500 mg_."
    return dosis, None


def validar_motivo(texto):
    motivo = texto.strip(" .,")
    if len(motivo) < 2 or len(motivo) > 60:
        return None, "Cuéntame en pocas palabras para qué es la cita, por ejemplo: _control de presión_."
    return motivo[0].upper() + motivo[1:], None


def interpretar_horas_medicamento(numero, texto):
    """Devuelve (lista_de_horas, None) o (None, mensaje_de_error)."""
    intervalo = extraer_intervalo(texto)

    if intervalo is None:
        relativa = extraer_hora_relativa(texto)
        horas = [relativa] if relativa else extraer_horas(texto)
        if not horas:
            return None, ("No logré entender la hora 😅 Escríbela así: _8 am_, _8am y 8pm_, "
                          "_cada 8 horas_ o _en 2 horas_.")
        return horas, None

    if intervalo not in INTERVALOS_VALIDOS:
        return None, ("Para intervalos puedo usar *cada 2, 3, 4, 6, 8, 12 o 24 horas* "
                      "(los que cuadran exacto en el día). Para otro caso, dime las horas exactas.")

    # ¿Desde qué hora? "cada 8 horas desde las 7am" / "empezando en 1 hora". Si no dice, al despertar.
    sin_intervalo = re.sub(r"cada \S+ ?\w*", " ", normalizar(texto))
    inicio = extraer_hora_relativa(sin_intervalo) or (extraer_horas(sin_intervalo) or [None])[0]
    if inicio is None:
        inicio = datos.obtener_perfil(numero)["despertar"]
    return generar_horas_periodicas(inicio, intervalo), None


def interpretar_una_hora(texto):
    relativa = extraer_hora_relativa(texto)
    horas = [relativa] if relativa else extraer_horas(texto)
    if len(horas) != 1:
        return None, "Dime *una* sola hora, por ejemplo: _9:30 am_ o _en 2 horas_."
    return horas[0], None


def interpretar_fecha_y_hora(texto):
    """'el lunes a las 3pm' -> (fecha, '15:00', None). La hora es opcional."""
    fecha = extraer_fecha(texto)
    relativa = extraer_hora_relativa(texto)
    if fecha is None and relativa:  # "en 2 horas" -> hoy
        fecha = date.today()
    if fecha is None:
        return None, None, "No entendí la fecha 😅 Prueba así: _15/10_, _mañana_ o _el próximo lunes_."
    if fecha < date.today():
        return None, None, "Esa fecha ya pasó. ¿Me das la fecha correcta de la cita?"
    horas = [relativa] if relativa else extraer_horas(texto, estricto=True)
    return fecha, (horas[0] if len(horas) == 1 else None), None


def validar_momento_cita(fecha, hora):
    if fecha == date.today() and hora <= datetime.now().strftime("%H:%M"):
        return "Esa hora de hoy ya pasó. ¿A qué hora es la cita?"
    return None


def aplicar_cambios_medicamento(numero, med, texto):
    """Aplica al borrador lo que el usuario pidió cambiar. Devuelve (hubo_cambios, error)."""
    campos = extraer_campos(texto, ETIQUETAS_MED)
    # Sin etiquetas, pero parece un horario ("cada 6 horas", "9pm"): lo tomamos como horas
    if not campos and (extraer_intervalo(texto) or extraer_hora_relativa(texto) or extraer_horas(texto, estricto=True)):
        campos = {"horas": texto}
    nuevos = {}
    for campo, valor in campos.items():
        if campo == "nombre":
            nuevos["nombre"], error = validar_nombre(valor)
        elif campo == "dosis":
            nuevos["dosis"], error = validar_dosis(valor)
        else:
            nuevos["horas"], error = interpretar_horas_medicamento(numero, valor)
        if error:
            return False, error
    med.update(nuevos)  # solo se aplica si TODO fue válido
    return bool(nuevos), None


def aplicar_cambios_cita(cita, texto):
    campos = extraer_campos(texto, ETIQUETAS_CITA)
    if not campos:
        fecha, hora, _ = interpretar_fecha_y_hora(texto)
        if fecha and extraer_fecha(texto):
            campos["fecha"] = texto
        elif extraer_hora_relativa(texto) or extraer_horas(texto, estricto=True):
            campos["hora"] = texto
    nuevos = {}
    for campo, valor in campos.items():
        if campo == "motivo":
            nuevos["motivo"], error = validar_motivo(valor)
        elif campo == "fecha":
            fecha, hora, error = interpretar_fecha_y_hora(valor)
            if not error:
                nuevos["fecha"] = fecha
                if hora and "hora" not in campos:
                    nuevos["hora"] = hora
        else:
            nuevos["hora"], error = interpretar_una_hora(valor)
        if error:
            return False, error
    if nuevos:
        error = validar_momento_cita(nuevos.get("fecha", cita["fecha"]), nuevos.get("hora", cita["hora"]))
        if error:
            return False, error
    cita.update(nuevos)
    return bool(nuevos), None


# ======================================================================
# Resúmenes
# ======================================================================

def resumen_medicamento(numero, med, titulo):
    return (f"📝 {titulo}:\n"
            f"💊 *{med['nombre']}* — {med['dosis']}\n"
            f"⏰ {horas_legibles(med['horas'])}\n"
            f"{aviso_horas_de_sueno(numero, med['horas'])}\n"
            "¿Lo guardo? Responde *sí*, *no*, o dime qué cambiar (ej: _hora 9pm_).")


def resumen_cita(cita, titulo):
    return (f"📝 {titulo}:\n"
            f"🩺 *{cita['motivo']}*\n"
            f"📅 {fecha_legible(cita['fecha'])} a las {hora_legible(cita['hora'])}\n\n"
            "¿La guardo? Responde *sí*, *no*, o dime qué cambiar (ej: _hora 10am_).")


def aviso_horas_de_sueno(numero, horas):
    """Si alguna toma cae mientras duerme, lo avisa pero NO la quita: eso lo decide el médico."""
    perfil = datos.obtener_perfil(numero)
    dormido = [h for h in horas if not esta_despierto(h, perfil["despertar"], perfil["dormir"])]
    if not dormido:
        return ""
    return (f"\n🌙 Ojo: la toma de las {horas_legibles(dormido)} cae en tu horario de sueño. "
            "No la quité, porque cambiar el horario de un medicamento lo decide tu médico.\n")


# ======================================================================
# Listados, selección y perfil
# ======================================================================

def texto_medicamentos(numero):
    medicamentos = datos.listar_medicamentos(numero)
    if not medicamentos:
        return "💊 Aún no tienes medicamentos registrados. Escribe *1* para registrar uno."
    partes = ["💊 *Tus medicamentos*"]
    for med in medicamentos:
        partes.append(f"\n*{med['nombre']}* — {med['dosis']}\n⏰ {horas_legibles(med['horas'])}")
    corazones = texto_corazones(numero)
    if corazones:
        partes.append("\n" + corazones)
    return "\n".join(partes)


def texto_citas(numero):
    citas = datos.listar_citas(numero, date.today().isoformat())
    if not citas:
        return "📅 No tienes citas próximas. Escribe *3* para registrar una."
    partes = ["📅 *Tus próximas citas*"]
    for cita in citas:
        fecha = date.fromisoformat(cita["fecha"])
        aviso = "ya te la recordé" if cita["recordada"] else "te la recuerdo el día anterior"
        partes.append(f"\n🩺 *{cita['motivo']}*\n{fecha_legible(fecha)}, {hora_legible(cita['hora'])}\n_({aviso})_")
    return "\n".join(partes)


def obtener_opciones(numero, filtro=None):
    opciones = []
    if filtro in (None, "med"):
        for med in datos.listar_medicamentos(numero):
            opciones.append({"tipo": "med", "id": med["id"],
                             "descripcion": f"💊 {med['nombre']} ({horas_legibles(med['horas'])})"})
    if filtro in (None, "cita"):
        for cita in datos.listar_citas(numero, date.today().isoformat()):
            fecha = date.fromisoformat(cita["fecha"])
            opciones.append({"tipo": "cita", "id": cita["id"],
                             "descripcion": f"📅 {cita['motivo']}, {fecha_legible(fecha)}"})
    return opciones


def iniciar_seleccion(numero, sesion, accion, filtro):
    opciones = obtener_opciones(numero, filtro)
    if not opciones:
        return f"No tienes nada para {accion} 📭 Escribe *menu* para ver opciones."

    sesion["temp"]["opciones"] = opciones
    if accion == "editar" and len(opciones) == 1:  # solo hay uno: no hace falta preguntar cuál
        cargar_para_editar(numero, sesion, opciones[0])
        return pedir_cambios(numero, sesion)

    sesion["estado"] = "EDITAR_ELEGIR" if accion == "editar" else "ELIMINAR_ELEGIR"
    lineas = [f"{i}. {o['descripcion']}" for i, o in enumerate(opciones, start=1)]
    extra = "" if accion == "editar" else "\n\nPuedes elegir varios (ej: _1 y 3_) o *todos*."
    return f"¿Qué quieres {accion}? Escribe el número:\n\n" + "\n".join(lineas) + extra


def elegir_una(opciones, texto):
    if texto and texto.isdigit() and 1 <= int(texto) <= len(opciones):
        return opciones[int(texto) - 1]
    return None


def elegir_varias(opciones, t):
    if contiene(t, "todos") or contiene(t, "todo") or contiene(t, "todas"):
        return list(opciones)
    numeros = [int(n) for n in re.findall(r"\d+", t)]
    if not numeros or any(not 1 <= n <= len(opciones) for n in numeros):
        return None
    return [opciones[n - 1] for n in sorted(set(numeros))]


def cargar_para_editar(numero, sesion, opcion):
    """Copia el registro elegido a un borrador; se edita el borrador y al confirmar se guarda."""
    if opcion["tipo"] == "med":
        med = next(m for m in datos.listar_medicamentos(numero) if m["id"] == opcion["id"])
        sesion["temp"]["med"] = {"id": med["id"], "nombre": med["nombre"],
                                 "dosis": med["dosis"], "horas": med["horas"]}
        sesion["estado"] = "MED_CONFIRMAR"
    else:
        cita = next(c for c in datos.listar_citas(numero, "0000-00-00") if c["id"] == opcion["id"])
        sesion["temp"]["cita"] = {"id": cita["id"], "motivo": cita["motivo"],
                                  "fecha": date.fromisoformat(cita["fecha"]), "hora": cita["hora"]}
        sesion["estado"] = "CITA_CONFIRMAR"


def pedir_cambios(numero, sesion):
    if sesion["estado"] == "MED_CONFIRMAR":
        med = sesion["temp"]["med"]
        return (f"✏️ Editando *{med['nombre']}* — {med['dosis']}, {horas_legibles(med['horas'])}\n\n"
                "Dime lo que quieras cambiar, uno o varios a la vez. Por ejemplo:\n"
                "_hora 9pm_ · _dosis 2 pastillas_ · _nombre Ibuprofeno y hora cada 8 horas_")
    cita = sesion["temp"]["cita"]
    return (f"✏️ Editando *{cita['motivo']}* — {fecha_legible(cita['fecha'])}, {hora_legible(cita['hora'])}\n\n"
            "Dime lo que quieras cambiar, uno o varios a la vez. Por ejemplo:\n"
            "_hora 10am_ · _fecha el próximo lunes_ · _motivo dentista y fecha 20/10_")


def texto_perfil(numero, sesion):
    perfil = datos.obtener_perfil(numero)
    contacto = (f"{perfil['contacto_nombre']}: {telefono_legible(perfil['contacto_numero'])}"
                if perfil["contacto_numero"] else "sin configurar")
    sesion["estado"] = "PERFIL_ELEGIR"
    return (f"⚙️ *Tu perfil*\n"
            f"☀️ Te levantas: {hora_legible(perfil['despertar'])}\n"
            f"🌙 Te duermes: {hora_legible(perfil['dormir'])}\n"
            f"📞 Contacto de emergencia: {contacto}\n\n"
            "¿Qué quieres configurar?\n1. Horario de sueño\n2. Contacto de emergencia")


def iniciar_horario(sesion):
    sesion["estado"] = "HORARIO_DESPERTAR"
    return "☀️ ¿A qué hora te levantas normalmente? (ej: _6:30 am_)"


def detectar_lugar(t):
    for clave, nombre in LUGARES.items():
        if re.search(rf"\b{clave}(s|es)?\b", t):
            return nombre
    return None