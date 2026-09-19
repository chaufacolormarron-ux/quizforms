"""Prueba rápida de QuizForms sin abrir Streamlit."""
import os
import tempfile
from pathlib import Path

from parser import parse_questions

sample = """1. ¿Cuál es correcta?
A) Uno
B) Dos
C) Tres
D) Cuatro
Respuesta: B
Puntos: 2

2. La prueba funciona.
Respuesta: Verdadero
Puntos: 1

Tipo: Premisas
Pregunta: Selecciona la combinación:
Premisa A: Alfa
Premisa B: Beta
Respuesta: C
Puntos: 2
Fin pregunta
"""

questions = parse_questions(sample)
assert len(questions) == 3
assert questions[0]["type"] == "multiple_choice"
assert questions[0]["answer"] == "B"
assert questions[0]["points"] == 2.0
assert questions[1]["type"] == "true_false"
assert questions[2]["type"] == "premises"

print("Parser: OK")
print("Preguntas detectadas:", len(questions))
print("QuizForms v0.7: prueba básica superada")
