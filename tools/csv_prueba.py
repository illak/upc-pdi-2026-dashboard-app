#!/usr/bin/env python3
"""Genera un CSV de prueba con la MISMA estructura que la pestaña "data" del
formulario, para ver el tablero con datos sin tocar la planilla real.

Estructura verificada de la planilla (pestaña "data"):
    Marca temporal | Unidad Académica o área de pertenencia
                   | Claustro al que pertenece | Rol o función, en la UPC
    (no hay columna de correos)

Uso:
    python3 tools/csv_prueba.py                       # 180 respuestas -> web/data/pruebas.csv
    python3 tools/csv_prueba.py 400                   # otro volumen
    python3 tools/csv_prueba.py 180 /tmp/otro.csv     # otro destino

Después se mira en el tablero con:
    ?fuente=csv&url=data/pruebas.csv
"""
import csv
import datetime as dt
import os
import random
import sys

# Opciones del formulario, tal cual llegan en la respuesta.
SEDES = [
    "Sede Regional Bell Ville - Mariano Moreno",
    "Sede Regional Morteros - María Justa Moyano de Ezpeleta",
    "Sede Regional Río Tercero",
    "Sede Regional Laboulaye - Eduardo Lefebvre",
    "Sede Regional Capilla del Monte - Dr. Bernardo Houssay",
    "Sede Regional Deán Funes - Juan Bautista Alberdi",
    "Sede Regional Villa Dolores - Luis Tessandori",
    "Sede Regional Villa Carlos Paz - Arturo Umberto Illia - ISAUI",
    "Sede Regional Cruz del Eje - Arturo Capdevila",
    "Sede Regional Mina Clavero - Dr. Carlos María Carena",
    "Sede Regional Las Varillas - Dalmacio Vélez Sarsfield",
    "Sede Regional Marcos Juárez - Bernardo Houssay",
]
INTERNAS = [
    "Rectorado",
    "Jefatura de Gabinete",
    "Secretaría Académica y de Posgrado",
    "Secretaría de Extensión",
    "Secretaría de Ciencia, Arte y Tecnología",
    "Secretaría de Bienestar Estudiantil y Graduados",
    "Secretaría de Coordinación y Asuntos Legales",
    "Secretaría de Administración y Recursos Humanos",
    "Facultad de Arte y Diseño",
    "Facultad de Educación y Salud",
    "Facultad de Educación Física",
    "Facultad de Turismo y Ambiente",
    "Instituto de Gestión e Innovación Tecnológica y Productiva",
]
# Respuestas libres del "Otro" (texto que escribe la persona)
LIBRES = [
    "Otro: Polo Cultural Ciudad de las Artes",
    "Otro: Escuela Superior de Artes Aplicadas Lino Enea Spilimbergo",
]

CLAUSTRROS = [("Docente", .46), ("No docente", .24), ("Estudiantil", .20), ("Graduados", .10)]
ROLES = {
    "Docente": [("Docente", .62),
                ("Dirección o Coordinación de carrera", .14),
                ("Dirección o Coordinación de área", .11),
                ("Secretaria o Secretario", .07),
                ("Autoridad institucional", .04),
                ("Estudiante de posgrado", .02)],
    "No docente": [("Personal no docente", .66),
                   ("Dirección o Coordinación de área", .14),
                   ("Secretaria o Secretario", .10),
                   ("Autoridad institucional", .06),
                   ("Docente", .04)],
    "Estudiantil": [("Estudiante de pregrado y/o grado", .78),
                    ("Estudiante de posgrado", .12),
                    ("Docente", .06),
                    ("Autoridad institucional", .04)],
    "Graduados": [("Graduado", .72),
                  ("Docente", .18),
                  ("Dirección o Coordinación de carrera", .10)],
}
# Pesos por sede regional (las más grandes reciben más gente)
PESO_SEDE = {
    "Villa Carlos Paz": 2.2, "Río Tercero": 2.0, "Morteros": 1.8, "Bell Ville": 1.7,
    "Capilla del Monte": 1.6, "Deán Funes": 1.5, "Las Varillas": 1.5, "Laboulaye": 1.4,
    "Marcos Juárez": 1.2, "Villa Dolores": 1.2, "Cruz del Eje": 1.1, "Mina Clavero": 1.0,
}

ENCABEZADO = ["Marca temporal", "Unidad Académica o área de pertenencia",
              "Claustro al que pertenece", "Rol o función, en la UPC"]


def elegir(pares, rnd):
    r, acc = rnd.random(), 0.0
    for valor, peso in pares:
        acc += peso
        if r <= acc:
            return valor
    return pares[-1][0]


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 180
    destino = next((a for a in sys.argv[1:] if not a.isdigit()), "web/data/pruebas.csv")
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ruta = destino if os.path.isabs(destino) else os.path.join(raiz, destino)

    rnd = random.Random(2026)
    # jornada de 9:00 a 18:30, ingresos cada 20-70 s
    t = dt.datetime(2026, 9, 12, 9, 0, 0)
    filas = [ENCABEZADO]
    peso_capital = 0.55
    for i in range(n):
        if rnd.random() < peso_capital:
            unidad = rnd.choice(INTERNAS)
        elif i % 37 == 5:                                   # algunas respuestas libres
            unidad = rnd.choice(LIBRES)
        else:
            unidad = rnd.choices(SEDES, weights=[PESO_SEDE.get(s.split(" - ")[0].replace("Sede Regional ", ""), 1.0) for s in SEDES])[0]
        claustro = elegir(CLAUSTRROS, rnd)
        rol = elegir(ROLES[claustro], rnd)
        t += dt.timedelta(seconds=rnd.randint(20, 70))
        filas.append([t.strftime("%d/%m/%Y %H:%M:%S"), unidad, claustro, rol])

    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    with open(ruta, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(filas)

    print(f"{len(filas) - 1} respuestas de prueba -> {ruta}")
    print(f"columnas: {filas[0]}")


if __name__ == "__main__":
    main()