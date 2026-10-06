"""Prueba a Navi en la terminal, sin WhatsApp."""
import datos
from bot import procesar_mensaje

datos.inicializar()
NUMERO_PRUEBA = "50300000000"  # número falso, solo para pruebas

print("Navi en modo terminal. Escribe 'salir' para terminar.\n")
while True:
    texto = input("Tú: ")
    if texto.strip().lower() == "salir":
        break
    print("\nNavi:", procesar_mensaje(NUMERO_PRUEBA, texto), "\n")
