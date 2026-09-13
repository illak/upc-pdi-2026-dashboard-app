#!/usr/bin/env python3
"""Corrobora que cada opción del formulario se clasifique bien.

Toma los textos EXACTOS del formulario (formulario_google.pdf) y los pasa por las
mismas reglas que usa el tablero (`web/data/config.json` + `web/data/sedes.json`),
para detectar tres problemas silenciosos:

  1. una opción que no se reconoce y cae en "Otro";
  2. dos opciones distintas que terminan en el mismo valor (se sumarían entre sí);
  3. una opción clasificada en la categoría equivocada (p. ej. "Dirección o
     Coordinación de carrera" contada como "de área").

    python3 tools/verificar_mapeo.py

Salida esperada: "RESULTADO: OK".
"""
import json
import os
import re
import sys
import unicodedata

AQUI = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(AQUI)
WEB = os.path.join(APP, "web")

VERDE, ROJO, AMARILLO, RESET = "\033[32m", "\033[31m", "\033[33m", "\033[0m"

# ── textos EXACTOS del formulario (formulario_google.pdf) ────────────────────
UNIDADES = [
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
    # Ojo: en el formulario el guion va SIN espacios alrededor
    "Sede Regional Bell Ville-Mariano Moreno",
    "Sede Regional Morteros-María Justa Moyano de Ezpeleta",
    "Sede Regional Río Tercero",
    "Sede Regional Laboulaye-Eduardo Lefebvre",
    "Sede Regional Capilla del Monte-Dr. Bernardo Houssay",
    "Sede Regional Deán Funes-Juan Bautista Alberdi",
    "Sede Regional Villa Dolores-Luis Tessandori",
    "Sede Regional Villa Carlos Paz-Arturo Umberto Illia-ISAUI",
    "Sede Regional Cruz del Eje-Arturo Capdevila",
    "Sede Regional Mina Clavero-Dr. Carlos María Carena",
    "Sede Regional Las Varillas-Dalmacio Vélez Sarsfield",
    "Sede Regional Marcos Juárez-Bernardo Houssay",
]
# texto libre que se guarda cuando alguien elige "Otro:"
UNIDADES_LIBRES = ["Polo Cultural Ciudad de las Artes", "Escuela de Oficios"]

CLAUSTRROS = ["Docente", "Estudiantil", "No docente", "Graduados"]

ROLES = [
    "Autoridad institucional (Rectora, Vicerrector, Decana/o, Vicedecana/o, "
    "Director/a General de Sede, Director/a Académico/a de Sede)",
    "Secretaria o Secretario, en Rectorado o en Unidades Académicas "
    "(Por ej.: Secretario de Extensión)",
    "Dirección o Coordinación de área",
    "Dirección o Coordinación de carrera",
    "Docente",
    "Estudiante de pregrado y/o grado",
    "Estudiante de posgrado",
    "Personal no docente",
    "Graduado",
]
ROLES_LIBRES = ["Coordinador de comunicación"]


def sin_acentos(s):
    return "".join(c for c in unicodedata.normalize("NFD", str(s or ""))
                   if unicodedata.category(c) != "Mn")


def norm(s):
    """Misma normalización que datos.js / server.py."""
    return re.sub(r"\s+", " ", re.sub(r"\s*-\s*", "-", sin_acentos(s))).strip().lower()


def main():
    cfg = json.load(open(os.path.join(WEB, "data", "config.json"), encoding="utf-8"))
    sedes = json.load(open(os.path.join(WEB, "data", "sedes.json"), encoding="utf-8"))
    mapa = cfg.get("mapeo_unidad", {})
    reglas = cfg.get("reglas_rol", [])
    claustros_ok = ["Docente", "Estudiantil", "No docente", "Graduados"]

    def clasificar_unidad(v):
        for op in sedes["nodos"]:
            if norm(op) == norm(v):
                return op, "match exacto"
        for clave, destino in mapa.items():
            if norm(clave) in norm(v):
                return destino, f"palabra clave «{clave}»"
        return "Otro", "SIN RECONOCER"

    def clasificar_rol(v):
        for frag, destino in reglas:
            if norm(frag) in norm(v):
                return destino, f"«{frag}»"
        return "Otro", "SIN RECONOCER"

    def clasificar_claustro(v):
        for c in claustros_ok:
            if norm(c) == norm(v):
                return c, "match exacto"
        return "Sin dato", "SIN RECONOCER"

    fallas, avisos = [], []

    def revisar(titulo, valores, clasificar, esperados_libres=()):
        print(f"\n── {titulo} ──")
        usados = {}
        for v in valores:
            dest, como = clasificar(v)
            marca = f"{VERDE}✓{RESET}" if como != "SIN RECONOCER" else f"{ROJO}✗{RESET}"
            print(f"  {marca} {v[:62]:<64} -> {dest:<46} ({como})")
            if como == "SIN RECONOCER":
                fallas.append(f"{titulo}: «{v[:50]}» no se reconoce")
            usados.setdefault(dest, []).append(v)
        for dest, origenes in usados.items():
            if len(origenes) > 1:
                fallas.append(f"{titulo}: {len(origenes)} opciones caen en «{dest}»: {origenes}")
        # las opciones libres tienen que caer justamente en "Otro"/"Sin dato"
        for v in esperados_libres:
            dest, _ = clasificar(v)
            if dest not in ("Otro", "Sin dato"):
                fallas.append(f"{titulo}: el texto libre «{v}» se clasificó como «{dest}»")
            else:
                print(f"  {VERDE}✓{RESET} {v[:62]:<64} -> {dest:<46} (texto libre, correcto)")

    revisar("UNIDAD ACADÉMICA O ÁREA DE PERTENENCIA",
            UNIDADES + list(UNIDADES_LIBRES), clasificar_unidad)
    revisar("CLAUSTRRO AL QUE PERTENECE", CLAUSTRROS, clasificar_claustro)
    revisar("ROL O FUNCIÓN", ROLES + list(ROLES_LIBRES), clasificar_rol)

    # ¿todas las opciones del formulario tienen etiqueta corta para el mapa/paneles?
    etq = cfg.get("etiquetas_unidad", {})
    sin_etq = [u for u in UNIDADES if u not in etq]
    if sin_etq:
        avisos.append(f"sin nombre corto en etiquetas_unidad: {sin_etq}")
    sin_nodo = [u for u in UNIDADES if u not in sedes["nodos"]]
    if sin_nodo:
        fallas.append(f"opciones sin coordenada en sedes.json: {sin_nodo}")

    print()
    for f in fallas:
        print(f"  {ROJO}✗{RESET} {f}")
    for a in avisos:
        print(f"  {AMARILLO}!{RESET} {a}")
    if fallas:
        print(f"\nRESULTADO: {ROJO}FALLA{RESET} ({len(fallas)} problemas)")
        sys.exit(1)
    print(f"  {VERDE}✓{RESET} las {len(UNIDADES)} unidades, los {len(CLAUSTRROS)} claustros "
          f"y los {len(ROLES)} roles se clasifican sin ambigüedad")
    print(f"\nRESULTADO: {VERDE}OK{RESET}")


if __name__ == "__main__":
    main()
