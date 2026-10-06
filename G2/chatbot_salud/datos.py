import sqlite3

DB = "navi.db"


def _ejecutar(sql, parametros=()):
    """Ejecuta INSERT/UPDATE/DELETE. Devuelve cuántas filas afectó."""
    conexion = sqlite3.connect(DB)
    try:
        cursor = conexion.execute(sql, parametros)
        conexion.commit()
        return cursor.rowcount
    finally:
        conexion.close()


def _consultar(sql, parametros=()):
    """Ejecuta un SELECT. Devuelve una lista de diccionarios."""
    conexion = sqlite3.connect(DB)
    conexion.row_factory = sqlite3.Row
    try:
        return [dict(fila) for fila in conexion.execute(sql, parametros).fetchall()]
    finally:
        conexion.close()


def inicializar():
    """Crea las tablas si todavía no existen."""
    _ejecutar("""
        CREATE TABLE IF NOT EXISTS usuarios (
            numero          TEXT PRIMARY KEY,
            despertar       TEXT NOT NULL DEFAULT '06:00',
            dormir          TEXT NOT NULL DEFAULT '22:00',
            contacto_nombre TEXT,
            contacto_numero TEXT
        )
    """)
    # Un medicamento es UNA fila, con todas sus horas juntas: "08:00,16:00,00:00"
    _ejecutar("""
        CREATE TABLE IF NOT EXISTS medicamentos (
            id     INTEGER PRIMARY KEY AUTOINCREMENT,
            numero TEXT NOT NULL,
            nombre TEXT NOT NULL,
            dosis  TEXT NOT NULL,
            horas  TEXT NOT NULL
        )
    """)
    _ejecutar("""
        CREATE TABLE IF NOT EXISTS citas (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            numero    TEXT NOT NULL,
            motivo    TEXT NOT NULL,
            fecha     TEXT NOT NULL,           -- "YYYY-MM-DD"
            hora      TEXT NOT NULL,           -- "HH:MM"
            recordada INTEGER NOT NULL DEFAULT 0
        )
    """)
    # Cada vez que toca una dosis se crea una "toma" para saber si la tomó o no
    _ejecutar("""
        CREATE TABLE IF NOT EXISTS tomas (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            numero         TEXT NOT NULL,
            medicamento_id INTEGER NOT NULL,
            nombre         TEXT NOT NULL,
            dosis          TEXT NOT NULL,
            programada     TEXT NOT NULL,      -- "YYYY-MM-DD HH:MM"
            estado         TEXT NOT NULL DEFAULT 'pendiente',  -- pendiente / tomada / omitida
            proximo_aviso  TEXT                -- cuándo volver a avisar (NULL = ya no)
        )
    """)


def _con_lista_horas(medicamento):
    medicamento["horas"] = medicamento["horas"].split(",")
    return medicamento


# ---------- Usuarios (perfil) ----------

def obtener_perfil(numero):
    filas = _consultar("SELECT * FROM usuarios WHERE numero = ?", (numero,))
    if filas:
        return filas[0]
    return {"numero": numero, "despertar": "06:00", "dormir": "22:00",
            "contacto_nombre": None, "contacto_numero": None}


def _asegurar_usuario(numero):
    _ejecutar("INSERT OR IGNORE INTO usuarios (numero) VALUES (?)", (numero,))


def guardar_horario(numero, despertar, dormir):
    _asegurar_usuario(numero)
    _ejecutar("UPDATE usuarios SET despertar = ?, dormir = ? WHERE numero = ?", (despertar, dormir, numero))


def guardar_contacto(numero, nombre, telefono):
    _asegurar_usuario(numero)
    _ejecutar("UPDATE usuarios SET contacto_nombre = ?, contacto_numero = ? WHERE numero = ?",
              (nombre, telefono, numero))


# ---------- Medicamentos ----------

def agregar_medicamento(numero, nombre, dosis, horas):
    _ejecutar("INSERT INTO medicamentos (numero, nombre, dosis, horas) VALUES (?, ?, ?, ?)",
              (numero, nombre, dosis, ",".join(horas)))


def buscar_medicamento_por_nombre(numero, nombre):
    filas = _consultar("SELECT * FROM medicamentos WHERE numero = ? AND lower(nombre) = lower(?)",
                       (numero, nombre))
    return _con_lista_horas(filas[0]) if filas else None


def listar_medicamentos(numero):
    filas = _consultar("SELECT * FROM medicamentos WHERE numero = ? ORDER BY nombre", (numero,))
    return [_con_lista_horas(f) for f in filas]


def medicamentos_a_la_hora(hora):
    """Todos los medicamentos (de todos los usuarios) que tienen una toma a esta hora."""
    filas = _consultar("SELECT * FROM medicamentos WHERE horas LIKE ?", (f"%{hora}%",))
    return [m for m in map(_con_lista_horas, filas) if hora in m["horas"]]


def actualizar_medicamento(numero, id_medicamento, nombre, dosis, horas):
    filas = _ejecutar(
        "UPDATE medicamentos SET nombre = ?, dosis = ?, horas = ? WHERE id = ? AND numero = ?",
        (nombre, dosis, ",".join(horas), id_medicamento, numero))
    return filas > 0


def eliminar_medicamento(numero, id_medicamento):
    # Se filtra también por número: nadie puede borrar datos de otro usuario
    return _ejecutar("DELETE FROM medicamentos WHERE id = ? AND numero = ?", (id_medicamento, numero)) > 0


# ---------- Citas ----------

def agregar_cita(numero, motivo, fecha, hora):
    _ejecutar("INSERT INTO citas (numero, motivo, fecha, hora) VALUES (?, ?, ?, ?)",
              (numero, motivo, fecha, hora))


def listar_citas(numero, desde_fecha):
    """Solo citas desde hoy en adelante."""
    return _consultar("SELECT * FROM citas WHERE numero = ? AND fecha >= ? ORDER BY fecha, hora",
                      (numero, desde_fecha))


def citas_sin_recordar(fecha):
    return _consultar("SELECT * FROM citas WHERE fecha = ? AND recordada = 0", (fecha,))


def marcar_cita_recordada(id_cita):
    _ejecutar("UPDATE citas SET recordada = 1 WHERE id = ?", (id_cita,))


def actualizar_cita(numero, id_cita, motivo, fecha, hora):
    # Si cambia, se vuelve a recordar
    filas = _ejecutar(
        "UPDATE citas SET motivo = ?, fecha = ?, hora = ?, recordada = 0 WHERE id = ? AND numero = ?",
        (motivo, fecha, hora, id_cita, numero))
    return filas > 0


def eliminar_cita(numero, id_cita):
    return _ejecutar("DELETE FROM citas WHERE id = ? AND numero = ?", (id_cita, numero)) > 0


# ---------- Tomas (adherencia) ----------

def existe_toma(medicamento_id, programada):
    return bool(_consultar("SELECT id FROM tomas WHERE medicamento_id = ? AND programada = ?",
                           (medicamento_id, programada)))


def crear_toma(medicamento, programada, proximo_aviso):
    _ejecutar("""INSERT INTO tomas (numero, medicamento_id, nombre, dosis, programada, proximo_aviso)
                 VALUES (?, ?, ?, ?, ?, ?)""",
              (medicamento["numero"], medicamento["id"], medicamento["nombre"],
               medicamento["dosis"], programada, proximo_aviso))


def toma_pendiente(numero):
    """La toma pendiente más reciente del usuario, o None."""
    filas = _consultar("""SELECT * FROM tomas WHERE numero = ? AND estado = 'pendiente'
                          ORDER BY programada DESC LIMIT 1""", (numero,))
    return filas[0] if filas else None


def marcar_toma(id_toma, estado):
    _ejecutar("UPDATE tomas SET estado = ?, proximo_aviso = NULL WHERE id = ?", (estado, id_toma))


def posponer_toma(id_toma, proximo_aviso):
    _ejecutar("UPDATE tomas SET proximo_aviso = ? WHERE id = ?", (proximo_aviso, id_toma))


def tomas_para_reavisar(ahora):
    return _consultar("""SELECT * FROM tomas WHERE estado = 'pendiente'
                         AND proximo_aviso IS NOT NULL AND proximo_aviso <= ?""", (ahora,))


def marcar_omitidas(limite):
    """Pendientes, sin más avisos programados y más viejas que el límite -> omitidas."""
    _ejecutar("""UPDATE tomas SET estado = 'omitida'
                 WHERE estado = 'pendiente' AND proximo_aviso IS NULL AND programada <= ?""", (limite,))


def ultimas_tomas(numero, cantidad=7):
    """Últimas tomas ya resueltas, de la más vieja a la más nueva."""
    filas = _consultar("""SELECT estado FROM tomas WHERE numero = ? AND estado != 'pendiente'
                          ORDER BY programada DESC LIMIT ?""", (numero, cantidad))
    return list(reversed(filas))


# ---------- Privacidad ----------

def borrar_datos_usuario(numero):
    for tabla in ("medicamentos", "citas", "tomas", "usuarios"):
        _ejecutar(f"DELETE FROM {tabla} WHERE numero = ?", (numero,))