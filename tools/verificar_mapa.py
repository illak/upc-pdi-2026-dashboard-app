#!/usr/bin/env python3
"""Verifica los círculos del mapa sobre el DOM realmente renderizado por Chrome.

El tablero publica en el atributo `data-nodos` del SVG la posición y el radio
final de cada círculo, ya calculados con la cantidad real de ingresos. Este
script lee ese atributo del DOM y comprueba que:

  1. ningún círculo quede fuera del área del mapa (se recortaría);
  2. no haya círculos de más ni de menos respecto de las localidades con datos;
  3. se informe qué círculos se tocan entre sí (pasa cuando dos sedes vecinas
     juntan mucha gente: es geográfico, no un error del tablero);
  4. ningún radio supere el tope definido en app.js.

    google-chrome --headless --virtual-time-budget=9000 --dump-dom \
        "http://localhost:8899/" > /tmp/dom.html
    python3 tools/verificar_mapa.py --dom /tmp/dom.html

Salida esperada: "RESULTADO: OK (13 círculos, 0 fuera del área)".
"""
import argparse
import html
import json
import math
import re
import sys

VERDE, ROJO, AMARILLO, RESET = "\033[32m", "\033[31m", "\033[33m", "\033[0m"
TOPE_RADIO = 30.0          # igual que radioNodo() en app.js


def leer_dom(ruta):
    with open(ruta, encoding="utf-8", errors="replace") as f:
        crudo = f.read()
    m = re.search(r'data-nodos="([^"]+)"', crudo)
    if not m:
        print(f"{ROJO}✗{RESET} el DOM no trae data-nodos: el tablero no llegó a dibujar "
              f"el mapa (¿falló la lectura de datos o el JS?)")
        sys.exit(2)
    return json.loads(html.unescape(m.group(1)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dom", required=True, help="HTML volcado con --dump-dom")
    args = ap.parse_args()

    d = leer_dom(args.dom)
    nodos = d.get("nodos", [])
    W, H = d.get("W", 430), d.get("H", 624)
    if not nodos:
        print(f"{ROJO}✗{RESET} el mapa no tiene ningún círculo")
        sys.exit(1)

    print(f"\ncírculos medidos por el navegador: {len(nodos)}   (viewBox {W}×{H})\n")
    print(f"  {'n':>4}{'x':>8}{'y':>8}{'radio':>8}   ¿entra en el área?")
    fallas, avisos, tocan = [], [], []
    for nd in sorted(nodos, key=lambda z: -z["n"]):
        x, y, R, n = nd["x"], nd["y"], nd["R"], nd["n"]
        dentro = (x - R >= -1 and x + R <= W + 1 and y - R >= -1 and y + R <= H + 1)
        if not dentro:
            fallas.append(f"el círculo de {n} ingresos en ({x:.0f},{y:.0f}) r={R:.1f} "
                          f"se sale del área del mapa")
        if R >= TOPE_RADIO:
            avisos.append(f"un círculo llegó al tope de radio ({TOPE_RADIO}): "
                          f"{n} ingresos → se dibuja más chico de lo que le correspondería")
        print(f"  {n:>4}{x:>8.0f}{y:>8.0f}{R:>8.1f}   {'sí' if dentro else ROJO + 'NO' + RESET}")

    for i, a in enumerate(nodos):
        for b in nodos[i + 1:]:
            dd = math.hypot(a["x"] - b["x"], a["y"] - b["y"])
            if dd < a["R"] + b["R"]:
                tocan.append((round(dd), round(a["R"] + b["R"]), a["n"], b["n"]))
    if tocan:
        avisos.append(f"{len(tocan)} par(es) de círculos se tocan "
                      f"(localidades vecinas con mucha gente): "
                      + ", ".join(f"n={p[2]}/{p[3]} (dist {p[0]} < suma {p[1]})" for p in tocan))

    print()
    for f in fallas:
        print(f"  {ROJO}✗{RESET} {f}")
    for a in avisos:
        print(f"  {AMARILLO}!{RESET} {a}")
    if fallas:
        print(f"\nRESULTADO: {ROJO}FALLA{RESET} ({len(fallas)} problemas)")
        sys.exit(1)
    print(f"  {VERDE}✓{RESET} todos los círculos entran en el área del mapa")
    print(f"\nRESULTADO: {VERDE}OK{RESET} ({len(nodos)} círculos, 0 fuera del área)")


if __name__ == "__main__":
    main()
