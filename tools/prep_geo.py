#!/usr/bin/env python3
"""Prepara los geodatos que consume el tablero (una sola vez).

Entrada :  ../data/nomi_cordoba_prov.json        (polígono provincia, Nominatim)
           ../data/deptos_cordoba_osm.geojson    (26 departamentos, OSM)
           ../data/localidades_georef.json       (centroides oficiales georef)
Salida  :  web/data/mapa.json   -> provincia + departamentos simplificados
           web/data/sedes.json  -> opción del formulario -> coordenada

Sin dependencias: stdlib puro.
"""
import json, os, math

AQUI = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(AQUI)
FUENTE = os.path.join(APP, "..", "data")
WEB_DATA = os.path.join(APP, "web", "data")

# ---------------------------------------------------------------- Douglas-Peucker
def _d2(p, a, b):
    if a == b:
        return (p[0] - a[0]) ** 2 + (p[1] - a[1]) ** 2
    x, y = a
    dx, dy = b[0] - x, b[1] - y
    t = ((p[0] - x) * dx + (p[1] - y) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    px, py = x + t * dx, y + t * dy
    return (p[0] - px) ** 2 + (p[1] - py) ** 2


def simplificar(pts, tol):
    """Douglas-Peucker iterativo (sin recursión: Córdoba tiene anillos largos)."""
    if len(pts) < 3:
        return pts
    tol2 = tol * tol
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    pila = [(0, len(pts) - 1)]
    while pila:
        i, j = pila.pop()
        if j <= i + 1:
            continue
        imax, dmax = -1, -1.0
        for k in range(i + 1, j):
            d = _d2(pts[k], pts[i], pts[j])
            if d > dmax:
                imax, dmax = k, d
        if dmax > tol2:
            keep[imax] = True
            pila.append((i, imax))
            pila.append((imax, j))
    return [p for p, k in zip(pts, keep) if k]


def redondear(pts, dec=4):
    vistos, out = set(), []
    for x, y in pts:
        r = (round(x, dec), round(y, dec))
        if r != (out[-1] if out else None):
            out.append(r)
    if len(out) > 3 and out[0] != out[-1]:
        out.append(out[0])
    return [[r[0], r[1]] for r in out]


def anillos(geom, tol):
    """Normaliza Polygon/MultiPolygon a una lista plana de anillos simplificados."""
    t, c = geom["type"], geom["coordinates"]
    polis = [c] if t == "Polygon" else c
    res = []
    for poli in polis:
        for anillo in poli:
            s = simplificar([(float(p[0]), float(p[1])) for p in anillo], tol)
            if len(s) >= 4:
                res.append(redondear(s))
    return res


def area(anillo):
    a = 0.0
    for i in range(len(anillo) - 1):
        a += anillo[i][0] * anillo[i + 1][1] - anillo[i + 1][0] * anillo[i][1]
    return abs(a) / 2


def main():
    os.makedirs(WEB_DATA, exist_ok=True)

    # --- provincia ---------------------------------------------------------
    with open(os.path.join(FUENTE, "nomi_cordoba_prov.json"), encoding="utf-8") as f:
        prov = json.load(f)[0]["geojson"]
    prov_anillos = anillos(prov, 0.0022)

    # --- departamentos -----------------------------------------------------
    with open(os.path.join(FUENTE, "deptos_cordoba_osm.geojson"), encoding="utf-8") as f:
        deptos = json.load(f)
    dptos = []
    for feat in deptos["features"]:
        nombre = feat["properties"].get("nombre") or "?"
        an = anillos(feat["geometry"], 0.012)
        if not an:
            continue
        an.sort(key=area, reverse=True)
        dptos.append({"n": nombre, "a": an[0]})
    dptos.sort(key=lambda d: d["n"])

    # --- bbox --------------------------------------------------------------
    xs = [p[0] for r in prov_anillos for p in r]
    ys = [p[1] for r in prov_anillos for p in r]
    bbox = [round(min(xs), 4), round(min(ys), 4), round(max(xs), 4), round(max(ys), 4)]

    mapa = {"bbox": bbox, "provincia": prov_anillos,
            "departamentos": [d["a"] for d in dptos]}

    p_mapa = os.path.join(WEB_DATA, "mapa.json")
    with open(p_mapa, "w", encoding="utf-8") as f:
        json.dump(mapa, f, ensure_ascii=False, separators=(",", ":"), sort_keys=True)

    # --- sedes: opción del formulario -> coordenada -------------------------
    with open(os.path.join(FUENTE, "localidades_georef.json"), encoding="utf-8") as f:
        loc = json.load(f)

    def co(nombre):
        d = loc[nombre]
        return [round(d["lat"], 5), round(d["lon"], 5)], d["departamento"]

    CAPITAL = "Capital (Córdoba)"
    cap_ll, cap_dep = co(CAPITAL)

    # (etiqueta del formulario, localidad georef o None si va a la capital, tipo)
    OPCIONES = [
        ("Rectorado", None, "rectorado"),
        ("Jefatura de Gabinete", None, "rectorado"),
        ("Secretaría Académica y de Posgrado", None, "secretaria"),
        ("Secretaría de Extensión", None, "secretaria"),
        ("Secretaría de Ciencia, Arte y Tecnología", None, "secretaria"),
        ("Secretaría de Bienestar Estudiantil y Graduados", None, "secretaria"),
        ("Secretaría de Coordinación y Asuntos Legales", None, "secretaria"),
        ("Secretaría de Administración y Recursos Humanos", None, "secretaria"),
        ("Facultad de Arte y Diseño", None, "facultad"),
        ("Facultad de Educación y Salud", None, "facultad"),
        ("Facultad de Educación Física", None, "facultad"),
        ("Facultad de Turismo y Ambiente", None, "facultad"),
        ("Instituto de Gestión e Innovación Tecnológica y Productiva", None, "instituto"),
        ("Sede Regional Bell Ville - Mariano Moreno", "Bell Ville", "sede"),
        ("Sede Regional Morteros - María Justa Moyano de Ezpeleta", "Morteros", "sede"),
        ("Sede Regional Río Tercero", "Río Tercero", "sede"),
        ("Sede Regional Laboulaye - Eduardo Lefebvre", "Laboulaye", "sede"),
        ("Sede Regional Capilla del Monte - Dr. Bernardo Houssay", "Capilla del Monte", "sede"),
        ("Sede Regional Deán Funes - Juan Bautista Alberdi", "Deán Funes", "sede"),
        ("Sede Regional Villa Dolores - Luis Tessandori", "Villa Dolores", "sede"),
        ("Sede Regional Villa Carlos Paz - Arturo Umberto Illia - ISAUI", "Villa Carlos Paz", "sede"),
        ("Sede Regional Cruz del Eje - Arturo Capdevila", "Cruz del Eje", "sede"),
        ("Sede Regional Mina Clavero - Dr. Carlos María Carena", "Mina Clavero", "sede"),
        ("Sede Regional Las Varillas - Dalmacio Vélez Sarsfield", "Las Varillas", "sede"),
        ("Sede Regional Marcos Juárez - Bernardo Houssay", "Marcos Juárez", "sede"),
    ]

    sedes = {}
    for etiqueta, localidad, tipo in OPCIONES:
        if localidad is None:
            ll, dep = cap_ll, cap_dep
        else:
            ll, dep = co(localidad)
        sedes[etiqueta] = {"lat": ll[0], "lon": ll[1], "dep": dep, "tipo": tipo,
                           "corta": etiqueta.replace("Sede Regional ", "").split(" - ")[0]
                           if tipo == "sede" else etiqueta}

    # alias de nombres cortos (la sede se nombra por su localidad en el mapa)
    for etiqueta, localidad, tipo in OPCIONES:
        if tipo == "sede":
            sedes[etiqueta]["corta"] = localidad

    meta = {"capital": {"lat": cap_ll[0], "lon": cap_ll[1], "dep": cap_dep},
            "nodos": sedes,
            "palabra_clave_capital": "Capital"}

    p_sedes = os.path.join(WEB_DATA, "sedes.json")
    with open(p_sedes, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1, sort_keys=True)

    # --- informe -----------------------------------------------------------
    print(f"provincia   : {len(prov_anillos)} anillo(s), "
          f"{sum(len(r) for r in prov_anillos)} puntos")
    print(f"departamentos: {len(dptos)} · {sum(len(d['a']) for d in dptos)} puntos")
    print(f"bbox        : {bbox}")
    print(f"sedes       : {len(sedes)} opciones "
          f"({sum(1 for v in sedes.values() if v['tipo'] == 'sede')} sedes regionales)")
    for p in (p_mapa, p_sedes):
        print(f"{os.path.relpath(p, APP):<28} {os.path.getsize(p)/1024:6.1f} KB")


if __name__ == "__main__":
    main()