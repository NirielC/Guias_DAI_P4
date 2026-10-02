import nltk
import string
import pickle
import random
import json
from nltk.stem import WordNetLemmatizer

lematizador = WordNetLemmatizer()

with open('model.pkl', 'rb') as f:
    vectorizar, le, model = pickle.load(f)

with open('intenciones.json', 'r', encoding='uft-8') as file:
    data = json.load(file)

def preproceso(oracion):
    oracion = oracion.lower()
    oracion = ''.join([char for char in oracion if char not in string.punctuation])
    tokens = nltk.word_tokenize(oracion)
    tokens = [lematizador.lemmatize(word) for word in tokens if word not in nltk.corpus.stopwords.words('spanish')]
    return ' '.join(tokens)

def obtener_respuesta(entrada_usuario):
    entrada_procesada = preproceso(entrada_usuario)
    x = vectorizar.transform([entrada_procesada])
    confianza = model.predict_proba(x)[0]
    max_conf_index = confianza.argmax()
    max_conf = confianza[max_conf_index]
    etiqueta = le.inverse_transform([max_conf_index])[0]

    print(f"Confianza: {max_conf}, Etiqueta: {etiqueta}")

    if max_conf < 0.4:
        return "Lo siento, no entendí lo que quisiste decir."
    else:
        for intencion in data['intenciones']:
            if intencion['etiqueta'] == etiqueta:
                return random.choice(intencion['respuestas'])

def chat():
    print("¡Hola! Spy Chatty. Escribe 'salir' para terminar la conversación.")
    while True:
        entrada_usuario = input("Tú: ")
        if entrada_usuario.lower() == 'salir':
            print("Chatty: ¡Hasta Luego!")
            break
        respuesta = obtener_respuesta(entrada_usuario)
        print(f"Chatty: {respuesta}")

chat()