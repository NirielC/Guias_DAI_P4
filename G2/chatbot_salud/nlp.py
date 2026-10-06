"""Procesamiento del lenguaje: limpiar texto, detectar intención y extraer entidades."""
import calendar
import re
import unicodedata
from datetime import date, datetime, timedelta
from difflib import get_close_matches
from urllib.parse import quote


# ---------- Limpieza del texto ----------

def _sin_tilde(caracter):
    return "".join(c for c in unicodedata.normalize("NFD", caracter) if unicodedata.category(c) != "Mn")


def plano(texto):
    """Minúsculas y sin tildes, pero con el MISMO largo que el original (sirve para ubicar posiciones)."""
    return "".join((_sin_tilde(c) or c).lower()[:1] for c in texto)


def normalizar(texto):
    """Minúsculas, sin tildes y sin signos raros. 'Medicación!!' -> 'medicacion'"""
    texto = plano(texto.strip())
    texto = re.sub(r"[^a-z0-9:/\- ]", " ", texto)  # deja letras, números, : / -
    return re.sub(r"\s+", " ", texto).strip()


def contiene(texto, frase):
    """True si la frase aparece como palabra(s) completa(s). Evita que 'ver' encaje en 'verdad'."""
    return f" {frase} " in f" {texto} "


# ---------- Números escritos con letras ----------
NUMEROS_TEXTO = {"un par de": 2, "par de": 2, "un": 1, "una": 1, "uno": 1, "dos": 2, "tres": 3,
                 "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10,
                 "quince": 15, "veinte": 20, "treinta": 30, "cuarenta": 40, "cincuenta": 50}
_NUM = r"(\d{1,3}|un par de|par de|" + "|".join(k for k in NUMEROS_TEXTO if " " not in k) + r")"


def _a_numero(texto):
    return int(texto) if texto.isdigit() else NUMEROS_TEXTO[texto]


# ---------- Intenciones ----------
# El orden importa: se revisan de arriba hacia abajo y gana la primera que coincida.
INTENCIONES = {
    "borrar_datos": ["borrar mis datos", "eliminar mis datos", "borra mis datos"],
    "confirmar_toma": ["tome", "ya tome", "ya la tome", "ya me la tome", "tomada", "ya me tome"],
    "posponer": ["posponer", "pospon", "posponla", "despues", "mas tarde", "en un rato",
                 "recuerdame", "recuerdamelo"],
    "perfil": ["perfil", "mi perfil", "horario", "mi horario", "me levanto", "me duermo",
               "despertar", "dormir", "contacto", "contacto de emergencia", "configurar"],
    "editar": ["editar", "cambiar", "modificar", "corregir", "edita", "cambia"],
    "eliminar": ["eliminar", "borrar", "quitar", "elimina", "borra", "quita"],
    "ver_citas": ["mis citas", "ver citas", "ver mis citas", "citas pendientes"],
    "ver_medicamentos": ["mis medicamentos", "mis medicinas", "mis pastillas", "ver medicamentos",
                         "ver mis medicamentos", "ver medicinas"],
    "ver": ["ver", "recordatorios", "mis recordatorios", "que tengo", "lista", "resumen",
            "progreso", "corazones"],
    "registrar_cita": ["cita", "citas", "consulta", "doctor", "doctora", "medico", "control"],
    "buscar_lugar": ["farmacia", "farmacias", "hospital", "hospitales", "clinica", "clinicas",
                     "unidad de salud", "laboratorio", "cerca", "buscar", "donde"],
    "registrar_medicamento": ["medicamento", "medicamentos", "medicina", "medicinas", "medicacion",
                              "pastilla", "pastillas", "remedio", "tratamiento",
                              "jarabe", "pildora", "capsula"],
    "ayuda": ["ayuda", "help", "como funciona", "no entiendo", "instrucciones"],
    "despedida": ["gracias", "adios", "chao", "bye", "hasta luego", "no gracias", "nos vemos"],
    "menu": ["hola", "menu", "inicio", "buenas", "buenos dias", "buenas tardes",
             "buenas noches", "hey", "ola", "que tal"],
}

OPCIONES_MENU = {"1": "registrar_medicamento", "2": "ver_medicamentos", "3": "registrar_cita",
                 "4": "ver_citas", "5": "editar", "6": "eliminar", "7": "perfil", "8": "buscar_lugar"}

PALABRAS_EMERGENCIA = ["emergencia", "dolor de pecho", "no puedo respirar", "me desmaye",
                       "desmayo", "sobredosis", "convulsion", "infarto", "me ahogo",
                       "sangrado fuerte", "auxilio"]

# Palabra -> intención, solo palabras sueltas de 4+ letras (para tolerar errores de dedo)
_PALABRAS_SUELTAS = {
    palabra: intencion
    for intencion, lista in INTENCIONES.items()
    for palabra in lista
    if " " not in palabra and len(palabra) >= 4
}


def es_emergencia(t):
    return any(contiene(t, p) for p in PALABRAS_EMERGENCIA)


def detectar_intencion(t, aproximado=True):
    """Recibe texto normalizado. Devuelve el nombre de la intención o None.
    aproximado=False desactiva la tolerancia a errores de dedo."""
    # 1) Número del menú: "1", "opcion 1"
    numero = re.fullmatch(r"(?:opcion )?([1-8])", t)
    if numero:
        return OPCIONES_MENU[numero.group(1)]

    # 2) Coincidencia exacta de palabras o frases
    for intencion, frases in INTENCIONES.items():
        if any(contiene(t, frase) for frase in frases):
            return intencion

    # 3) Coincidencia aproximada (errores de dedo): "medicamneto" -> "medicamento"
    if not aproximado:
        return None
    for palabra in t.split():
        if len(palabra) < 4:
            continue
        parecida = get_close_matches(palabra, _PALABRAS_SUELTAS.keys(), n=1, cutoff=0.8)
        if parecida:
            return _PALABRAS_SUELTAS[parecida[0]]
    return None


# ---------- Respuestas sí / no ----------
SI = {"si", "s", "claro", "dale", "ok", "okay", "correcto", "guardalo", "guardala", "simon", "va",
      "sale", "afirmativo", "yes", "exacto", "listo", "perfecto", "confirmo", "confirmar",
      "bueno", "sip", "obvio", "porfa", "elimina", "eliminalo", "borralo"}
SI_FRASES = ["esta bien", "asi esta bien", "de acuerdo", "por supuesto", "por favor", "de una",
             "todo bien", "asi esta"]
NO = {"no", "n", "nel", "incorrecto", "negativo", "nop", "nah", "cancela"}
NO_FRASES = ["mejor no", "no gracias", "dejalo asi", "olvidalo"]


def es_si(t):
    if not t:
        return False
    return t in SI or t.split()[0] in SI or any(contiene(t, f) for f in SI_FRASES)


def es_no(t):
    if not t:
        return False
    return t in NO or t.split()[0] in NO or any(contiene(t, f) for f in NO_FRASES)


# ---------- Entidad @hora ----------
_PATRON_HORA = re.compile(r"\b(\d{1,2})(?:[:h](\d{2}))?\s*(am|pm)?\b")
_MESES_REGEX = None  # se define abajo


def _quitar_no_horas(t):
    """Borra del texto números que NO son horas: fechas, 'en 3 dias', 'cada 8 horas'..."""
    t = re.sub(r"\b\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?\b", " ", t)
    t = re.sub(r"\b\d{1,2} de (" + "|".join(MESES) + r")(?: de \d{4})?\b", " ", t)
    t = re.sub(r"\bcada " + _NUM + r" ?(h|hr|hrs|hora|horas)\b", " ", t)
    t = re.sub(r"\b" + _NUM + r" (dia|dias|semana|semanas|mes|meses|minuto|minutos|min|hora|horas)\b", " ", t)
    t = re.sub(r"\bel \d{1,2}\b(?! ?(:|am|pm|de la))", " ", t)  # "el 20" (día del mes)
    return t


def extraer_horas(texto, estricto=False):
    """'8am y 8:30 pm' -> ['08:00', '20:30'].
    estricto=True: solo acepta horas que claramente son horas (con :, am/pm, 'a las', 'de la ...')."""
    texto = re.sub(r"(\d)\.(\d{2})", r"\1:\2", texto)  # "8.30" -> "8:30"
    t = normalizar(texto).replace("a m", "am").replace("p m", "pm")
    t = _quitar_no_horas(t)
    coincidencias = list(_PATRON_HORA.finditer(t))
    horas = []

    for m in coincidencias:
        h = int(m.group(1))
        minutos = int(m.group(2) or 0)
        sufijo = m.group(3)
        antes = t[max(0, m.start() - 8):m.start()]
        despues = t[m.end():m.end() + 20]

        # Sin am/pm: revisamos si dice "de la tarde/noche/mañana"
        if not sufijo:
            contexto = t if len(coincidencias) == 1 else despues
            if "tarde" in contexto or "noche" in contexto:
                sufijo = "pm"
            elif "manana" in contexto or "madrugada" in contexto:
                sufijo = "am"

        if estricto and not (m.group(2) or sufijo or "las" in antes or "la" in antes):
            continue
        if sufijo and not 1 <= h <= 12:
            continue  # "15 pm" no tiene sentido
        if sufijo == "pm" and h < 12:
            h += 12
        if sufijo == "am" and h == 12:
            h = 0
        if h > 23 or minutos > 59:
            continue

        hora = f"{h:02d}:{minutos:02d}"
        if hora not in horas:
            horas.append(hora)
    return sorted(horas)


def extraer_hora_relativa(texto, ahora=None):
    """'en 2 horas', 'en media hora', 'dentro de 30 minutos' -> 'HH:MM' contando desde ahora."""
    minutos = extraer_minutos_relativos(texto)
    if minutos is None:
        return None
    ahora = ahora or datetime.now()
    return (ahora + timedelta(minutes=minutos)).strftime("%H:%M")


def extraer_minutos_relativos(texto):
    """'en 2 horas' -> 120, 'en media hora' -> 30, 'posponer 15 min' -> 15. None si no hay."""
    t = normalizar(texto)
    if contiene(t, "media hora"):
        return 30
    if re.search(r"\bhora y media\b", t):
        return 90
    m = re.search(r"\b" + _NUM + r" (minuto|minutos|min|hora|horas)\b", t)
    if not m or contiene(t, "cada"):
        return None
    cantidad = _a_numero(m.group(1))
    return cantidad * 60 if m.group(2).startswith("hora") else cantidad


def extraer_intervalo(texto):
    """'cada 8 horas' / 'cada ocho horas' -> 8. None si no habla de un intervalo."""
    m = re.search(r"\bcada " + _NUM + r" ?(h|hr|hrs|hora|horas)\b", normalizar(texto))
    return _a_numero(m.group(1)) if m else None


def generar_horas_periodicas(inicio, intervalo):
    """('07:00', 8) -> ['07:00', '15:00', '23:00']"""
    h, m = map(int, inicio.split(":"))
    return sorted(f"{(h + intervalo * i) % 24:02d}:{m:02d}" for i in range(24 // intervalo))


def esta_despierto(hora, despertar, dormir):
    """True si la hora cae entre despertar y dormir. Funciona aunque duerma después de medianoche."""
    if despertar < dormir:
        return despertar <= hora < dormir
    return hora >= despertar or hora < dormir


def hora_legible(hhmm):
    """'20:30' -> '8:30 p. m.'"""
    h, m = map(int, hhmm.split(":"))
    return f"{h % 12 or 12}:{m:02d} {'a. m.' if h < 12 else 'p. m.'}"


def horas_legibles(horas):
    return ", ".join(hora_legible(h) for h in horas)


# ---------- Entidad @fecha ----------
MESES = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6, "julio": 7,
         "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12}
DIAS_SEMANA = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]


def _sumar_meses(fecha, meses):
    mes_total = fecha.month - 1 + meses
    anio, mes = fecha.year + mes_total // 12, mes_total % 12 + 1
    dia = min(fecha.day, calendar.monthrange(anio, mes)[1])  # 31 de enero + 1 mes = 28/29 feb
    return date(anio, mes, dia)


def extraer_fecha(texto, hoy=None):
    """'15/10', '15 de octubre', 'mañana', 'el próximo lunes', 'en 3 días', 'en un mes' -> date."""
    hoy = hoy or date.today()
    t = normalizar(texto)
    t = re.sub(r"\bde la (manana|tarde|noche|madrugada)\b", " ", t)  # eso es hora, no fecha

    if contiene(t, "pasado manana"):
        return hoy + timedelta(days=2)
    if contiene(t, "manana"):
        return hoy + timedelta(days=1)
    if contiene(t, "hoy"):
        return hoy

    # "en 3 dias", "en una semana", "en un mes", "dentro de 2 semanas"
    m = re.search(r"\b(?:en|dentro de) " + _NUM + r" (dia|dias|semana|semanas|mes|meses)\b", t)
    if m:
        n, unidad = _a_numero(m.group(1)), m.group(2)
        if unidad.startswith("dia"):
            return hoy + timedelta(days=n)
        if unidad.startswith("semana"):
            return hoy + timedelta(weeks=n)
        return _sumar_meses(hoy, n)
    if contiene(t, "proxima semana") or contiene(t, "la otra semana"):
        return hoy + timedelta(weeks=1)

    # "el lunes", "el próximo viernes"
    for indice, dia in enumerate(DIAS_SEMANA):
        if contiene(t, dia):
            dias_faltantes = (indice - hoy.weekday()) % 7 or 7  # si hoy es lunes, "el lunes" = el siguiente
            return hoy + timedelta(days=dias_faltantes)

    anio_escrito = None
    m = re.search(r"\b(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?\b", t)
    if m:
        dia, mes = int(m.group(1)), int(m.group(2))
        anio_escrito = int(m.group(3)) if m.group(3) else None
    else:
        m = re.search(r"\b(\d{1,2}) de (" + "|".join(MESES) + r")(?: de (\d{4}))?\b", t)
        if m:
            dia, mes = int(m.group(1)), MESES[m.group(2)]
            anio_escrito = int(m.group(3)) if m.group(3) else None
        else:
            m = re.search(r"\bel (\d{1,2})\b(?! ?(:|am|pm|de la))", t)  # "el 20" = día 20
            if not m:
                return None
            dia, mes = int(m.group(1)), hoy.month
            try:
                fecha = date(hoy.year, mes, dia)
            except ValueError:
                return None
            return fecha if fecha >= hoy else _sumar_meses(fecha, 1)

    if anio_escrito is not None and anio_escrito < 100:
        anio_escrito += 2000
    anio = anio_escrito or hoy.year
    try:
        fecha = date(anio, mes, dia)
    except ValueError:
        return None
    if anio_escrito is None and fecha < hoy:  # sin año y ya pasó: es el próximo año
        try:
            fecha = date(anio + 1, mes, dia)
        except ValueError:
            return None
    return fecha


def fecha_legible(fecha):
    """date -> 'lunes 12/10/2026'"""
    return f"{DIAS_SEMANA[fecha.weekday()].replace('miercoles', 'miércoles').replace('sabado', 'sábado')} {fecha.strftime('%d/%m/%Y')}"


# ---------- Edición en lenguaje natural: "nombre Ibuprofeno, hora 8pm" ----------

def extraer_campos(texto, etiquetas):
    """etiquetas = {'nombre': ['nombre', 'medicamento'], 'hora': ['hora', 'horas'], ...}
    'cambia el nombre a Ibuprofeno y la dosis a 2 pastillas' -> {'nombre': 'Ibuprofeno', 'dosis': '2 pastillas'}"""
    base = plano(texto)
    alias = {a: campo for campo, lista in etiquetas.items() for a in lista}
    patron = r"\b(" + "|".join(sorted(alias, key=len, reverse=True)) + r")\b\s*(?:(?:es|seria|sea|a|por)\b|[:=])?\s*"
    encontrados = []
    for m in re.finditer(patron, base):
        anterior = base[:m.start()].split()[-1:]  # palabra justo antes de la etiqueta
        # "cada 8 horas" o "en dos horas": ahí "horas" es parte del valor, no una etiqueta
        if anterior and (anterior[0].isdigit() or anterior[0] in NUMEROS_TEXTO or anterior[0] == "media"):
            continue
        encontrados.append(m)
    campos = {}
    for i, m in enumerate(encontrados):
        fin = encontrados[i + 1].start() if i + 1 < len(encontrados) else len(texto)
        valor = texto[m.end():fin]
        # quita conectores sueltos al final: ", y la", " y el", ","
        valor = re.sub(r"[\s,;]*(?:\b[yYeE]\b)?\s*(?:\b(?:la|el|los|las|La|El)\b)?[\s,;.]*$", "", valor).strip(" ,;.")
        if valor:
            campos[alias[m.group(1)]] = valor
    return campos


# ---------- Enlaces útiles ----------

def enlace_calendario(motivo, fecha, hora):
    """Abre Google Calendar con la cita ya llenada (1 hora de duración)."""
    h, m = map(int, hora.split(":"))
    inicio = datetime(fecha.year, fecha.month, fecha.day, h, m)
    fin = inicio + timedelta(hours=1)
    formato = "%Y%m%dT%H%M%S"
    return ("https://calendar.google.com/calendar/render?action=TEMPLATE"
            f"&text={quote('Cita médica: ' + motivo)}"
            f"&dates={inicio.strftime(formato)}/{fin.strftime(formato)}"
            f"&details={quote('Recordatorio creado por Navi')}"
            "&ctz=America/El_Salvador")


def enlace_mapa(busqueda):
    """Abre Google Maps buscando cerca de la ubicación del teléfono."""
    return f"https://www.google.com/maps/search/?api=1&query={quote(busqueda + ' cerca de mí')}"