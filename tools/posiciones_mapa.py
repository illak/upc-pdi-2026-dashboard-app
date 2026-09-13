#!/usr/bin/env python3
"""Imprime las posiciones ya proyectadas de cada nodo dentro del viewBox del mapa,
para poder decidir los desplazamientos de las etiquetas con números y no a ojo."""
import json, math, os

AQUI = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(os.path.dirname(AQUI), "web")

W, H, MARGEN = 430, 624, 20

mapa = json.load(open(os.path.join(WEB, "data", "mapa.json"), encoding="utf-8"))
sedes = json.load(open(os.path.join(WEB, "data", "sedes.json"), encoding="utf-8"))

x0, y0, x1, y1 = mapa["bbox"]
lat0 = (y0 + y1) / 2
kx = math.cos(math.radians(lat0))
px, py = (lambda lo: lo * kx), (lambda la: -la)
ax0, ax1, ay0, ay1 = px(x0), px(x1), py(y1), py(y0)
s = min((W - 2 * MARGEN) / (ax1 - ax0), (H - 2 * MARGEN) / (ay1 - ay0))
ox = (W - (ax1 - ax0) * s) / 2 - ax0 * s
oy = (H - (ay1 - ay0) * s) / 2 - ay0 * s


def proy(lon, lat):
    return px(lon) * s + ox, py(lat) * s + oy


print(f"escala {s:.2f} px/grado-ajustado · provincia "
      f"{(ax1-ax0)*s:.0f}×{(ay1-ay0)*s:.0f} en viewBox {W}×{H}")
print(f"margen libre: izq {proy(x0, 0)[0]:.0f} · der {W - proy(x1, 0)[0]:.0f} · "
      f"arriba {proy(0, y1)[1]:.0f} · abajo {H - proy(0, y0)[1]:.0f}\n")

vistos = {}
for nombre, d in sedes["nodos"].items():
    k = (round(d["lat"], 3), round(d["lon"], 3))
    vistos.setdefault(k, {"n": [], **d})
    vistos[k]["n"].append(d["corta"])

filas = []
for (la, lo), d in vistos.items():
    x, y = proy(lo, la)
    tipo = "SEDE" if d["tipo"] == "sede" else "CAPITAL"
    filas.append((y, x, d["corta"], tipo, d["dep"]))
for y, x, nom, tipo, dep in sorted(filas):
    lado = "izq" if x < 100 else ("der" if x > W - 100 else "centro")
    print(f"  x={x:6.1f}  y={y:6.1f}  {tipo:<7} {nom:<20} {dep:<28} [{lado}]")
