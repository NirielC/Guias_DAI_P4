import json
import nltk
import string 
import pickle
from nltk.stem import WordNetLemmatizer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import LabelEncoder
from sklearn.svm import SVC

lematizador = WordNetLemmatizer()

with open('intenciones.json', 'r', encoding='utf-8') as file:
    data = json.load(file)

oraciones = []
etiquetas = []
respuestas = {}

for intencion in data['intenciones']:
    for patron in intencion['patrones']:
        tokens = nltk.word_tokenize(patron)
        oraciones.append(' '.join(tokens))
        etiquetas.append(intencion['etiqueta'])
    respuestas[intencion['etiqueta']] = intencion['respuestas']

def preproceso(oracion):
    oracion = oracion.lower()
    oracion = ''.join([char for char in oracion if char not in string.punctuation])
    tokens = nltk.word_tokenize(oracion)
    tokens = [lematizador.lemmatize(word) for word in tokens if word not in nltk.corpus.stopwords.words('spanish')]
    return ' '.join(tokens)

oraciones_procesadas = [preproceso(oracion) for oracion in oraciones]

vectorizar = TfidfVectorizer()
x = vectorizar.fit_transform(oraciones_procesadas)

le = LabelEncoder()
y = le.fit_transform(etiquetas)

model = SVC(kernel='linear', probability=True, random_state=42)
model.fit(x, y)

with open('model.pkl', 'wb') as f:
    pickle.dump((vectorizar, le, model), f)

print("Modelo entrenado y guardado exitosamente")
