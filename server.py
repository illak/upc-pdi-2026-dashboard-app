#!/usr/bin/env python3
"""Tablero en vivo - Primera Jornada de Construcción Participativa del PDI (UPC).

Servidor HTTP sin dependencias (stdlib) que:
  1. lee las respuestas del formulario (Google Sheet / CSV local / generador demo),
  2. las normaliza y agrega,
  3. publica un snapshot JSON en /api/estado que consume el tablero del navegador.

Uso:
    python3 server.py                       # usa web/data/config.json (planilla.id)
    python3 server.py --demo                # datos simulados, sin red
    python3 server.py --csv respuestas.csv  # archivo local
    python3 server.py --sheet <ID>          # fuerza la planilla
    python3 server.py --exportar web/data/estado.json   # hornea el snapshot (sitio estático)
    python3 server.py --imprimir            # imprime un snapshot y sale (sin servidor)
"""
from __future__ import annotations

import argparse
import csv as csvmod
import datetime as dt
import hashlib
import json
import os
import random
import re
import sys
import threading
import time
import unicodedata
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

AQUI = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(AQUI, "web")
# la configuración vive dentro de web/ para que también la lea el navegador
# cuando el sitio se publica como estático (GitHub Pages, sin backend)
CONFIG = os.path.join(WEB, "data", "config.json")
TZ = dt.timezone(dt.timedelta(hours=-3))


# --------------------------------------------------------------------- utilidades
def sin_acentos(s: str) -> str:
    s = unicodedata.normalize("NFD", str(s or ""))
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def norm(s: str) -> str:
    # El guion se normaliza: en el formulario las sedes vienen como
    # "Sede Regional Bell Ville-Mariano Moreno" (sin espacios), así que "a - b" y
    # "a-b" tienen que compararse igual.
    s = re.sub(r"\s*-\s*", "-", sin_acentos(s))
    return re.sub(r"\s+", " ", s).strip().lower()


def limpiar(s) -> str:
    return re.sub(r"\s+", " ", str(s if s is not None else "")).strip()


def ahora() -> dt.datetime:
    return dt.datetime.now(TZ)


# --------------------------------------------------------------------- carga
def cargar_config() -> dict:
    with open(CONFIG, encoding="utf-8") as f:
        return json.load(f)


def cargar_sedes() -> dict:
    with open(os.path.join(WEB, "data", "sedes.json"), encoding="utf-8") as f:
        return json.load(f)


# --------------------------------------------------------------------- lectura
def leer_sheet(sheet_id: str, hoja: str, rango: str) -> list[list[str]]:
    sys.path.insert(0, AQUI)
    import gapi
    datos = gapi.sheets_values(sheet_id, rango, hoja or None)
    return datos.get("values", [])


def leer_csv(ruta: str) -> list[list[str]]:
    with open(ruta, newline="", encoding="utf-8-sig") as f:
        muestra = f.read(4096)
        f.seek(0)
        try:
            dialecto = csvmod.Sniffer().sniff(muestra, delimiters=",;\t")
        except csvmod.Error:
            dialecto = csvmod.excel
        return [fila for fila in csvmod.reader(f, dialecto)]


# --------------------------------------------------------------------- demo
T0_DEMO = time.time()


def filas_demo(cfg: dict, n: int) -> list[list[str]]:
    """Genera n respuestas verosímiles. Determinista respecto del índice: la fila i
    siempre tiene el mismo contenido y la misma hora (si no, el hash cambiaría en cada lectura)."""
    d = cfg.get("demo", {})
    azar = random.Random(d.get("semilla", 2026))
    sedes = [k for k, v in SEDES["nodos"].items() if v["tipo"] == "sede"]
    internas = [k for k, v in SEDES["nodos"].items() if v["tipo"] != "sede"]
    peso_capital = float(d.get("peso_capital", 0.52))
    claustros = [("Docente", 0.46), ("No docente", 0.24), ("Estudiantil", 0.20), ("Graduados", 0.10)]
    roles = {
        "Docente": [("Docente", .66), ("Dirección o Coordinación de carrera", .14),
                    ("Dirección o Coordinación de área", .10), ("Autoridad institucional", .04),
                    ("Secretaria o Secretario", .06)],
        "No docente": [("Personal no docente", .74), ("Dirección o Coordinación de área", .13),
                       ("Secretaria o Secretario", .08), ("Autoridad institucional", .05)],
        "Estudiantil": [("Estudiante de pregrado y/o grado", .82),
                        ("Estudiante de posgrado", .18)],
        "Graduados": [("Graduado", .86), ("Docente", .14)],
    }

    def elegir(pares):
        r, acc = azar.random(), 0.0
        for v, p in pares:
            acc += p
            if r <= acc:
                return v
        return pares[-1][0]

    ritmo = float(d.get("ritmo_s", 4.0))
    filas = []
    for i in range(n):
        if azar.random() < peso_capital:
            unidad = azar.choice(internas)
        else:
            unidad = azar.choice(sedes)
        claustro = elegir(claustros)
        rol = elegir(roles[claustro])
        t = dt.datetime.fromtimestamp(T0_DEMO, TZ) + dt.timedelta(seconds=i * ritmo)
        filas.append([
            t.strftime("%d/%m/%Y %H:%M:%S"),
            f"asistente{i + 1:03d}@upc.edu.ar",
            unidad,
            claustro,
            rol,
        ])
    return filas


# --------------------------------------------------------------------- normalización
CLAVES = ("hora", "correo", "unidad", "claustro", "rol")


def mapear_columnas(encabezado: list[str], cfg: dict) -> dict:
    """Ubica cada columna por palabra clave; si no hay encabezado, usa el orden del formulario."""
    reglas = cfg["planilla"]["columnas"]
    idx: dict[str, int] = {}
    enc = [norm(c) for c in encabezado]
    for clave, palabras in reglas.items():
        for j, c in enumerate(enc):
            if any(norm(p) in c for p in palabras):
                idx[clave] = j
                break
    # relleno por posición conocida del formulario (marca temporal, correo, unidad, claustro, rol)
    for k, pos in zip(CLAVES, range(5)):
        idx.setdefault(k, pos)
    return idx


def ubicar_unidad(valor: str, cfg: dict) -> str:
    """Devuelve la opción canónica del formulario, o 'Otro'."""
    v = norm(valor)
    if not v:
        return "Otro"
    for canonica in SEDES["nodos"]:
        if norm(canonica) == v:
            return canonica
    for clave, canonica in cfg.get("mapeo_unidad", {}).items():
        if norm(clave) in v:
            return canonica
    # texto libre ("Otro: ..."): intentar reconocer una localidad / sede / unidad
    return "Otro"


def canonizar_claustro(valor: str) -> str:
    v = norm(valor)
    for c in ("Docente", "Estudiantil", "No docente", "Graduados"):
        if norm(c) == v:
            return c
    if "no docente" in v:
        return "No docente"
    if "estudiant" in v:
        return "Estudiantil"
    if "graduad" in v:
        return "Graduados"
    if "docente" in v:
        return "Docente"
    return "Sin dato"


def canonizar_rol(valor: str, cfg: dict) -> str:
    v = norm(valor)
    if not v:
        return "Sin dato"
    for fragmento, canonico in cfg.get("reglas_rol", []):
        if norm(fragmento) in v:
            return canonico
    return "Otro"


def parsear_hora(txt: str):
    txt = limpiar(txt)
    for fmt in ("%d/%m/%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M",
                "%m/%d/%Y %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return dt.datetime.strptime(txt, fmt).replace(tzinfo=TZ)
        except ValueError:
            continue
    return None


def normalizar(filas: list[list[str]], cfg: dict) -> list[dict]:
    if not filas:
        return []
    es_encabezado = any(norm(p) in norm(" ".join(str(c) for c in filas[0]))
                        for p in ("marca temporal", "correo", "unidad", "claustro", "rol"))
    idx = mapear_columnas(filas[0], cfg) if es_encabezado else mapear_columnas([], cfg)
    cuerpo = filas[1:] if es_encabezado else filas

    registros = []
    for fila in cuerpo:
        if not any(limpiar(c) for c in fila):
            continue
        def celda(k):
            j = idx[k]
            return limpiar(fila[j]) if j < len(fila) else ""
        crudo_unidad = celda("unidad")
        unidad = ubicar_unidad(crudo_unidad, cfg)
        t = parsear_hora(celda("hora"))
        registros.append({
            "i": len(registros),
            "hora": t.strftime("%H:%M:%S") if t else celda("hora")[:8],
            "hora_iso": t.isoformat() if t else None,
            "clave_hora": t.timestamp() if t else 0.0,
            "unidad": unidad,
            "unidad_cruda": crudo_unidad,
            "claustro": canonizar_claustro(celda("claustro")),
            "rol": canonizar_rol(celda("rol"), cfg),
        })
    registros.sort(key=lambda r: (r["clave_hora"], r["i"]))
    for k, r in enumerate(registros):
        r["i"] = k
    return registros


# --------------------------------------------------------------------- agregación
def contar(registros, campo, orden=None):
    c: dict[str, int] = {}
    for r in registros:
        c[r[campo]] = c.get(r[campo], 0) + 1
    items = sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))
    if orden:
        pos = {k: i for i, k in enumerate(orden)}
        items.sort(key=lambda kv: (-kv[1], pos.get(kv[0], 99)))
    return [{"k": k, "n": n} for k, n in items]


def snapshot(registros: list[dict], cfg: dict, modo: str, error: str | None,
             version: int, t0: float) -> dict:
    etiquetas = cfg.get("etiquetas", {})
    vida = cfg["frecuencia"]["vida_pulso_s"]
    ahora_ts = time.time()

    unidades = []
    for item in contar(registros, "unidad"):
        s = SEDES["nodos"].get(item["k"])
        unidades.append({
            "k": item["k"], "n": item["n"],
            "lat": s["lat"] if s else None,
            "lon": s["lon"] if s else None,
            "dep": s["dep"] if s else None,
            "tipo": s["tipo"] if s else "otro",
            "corta": (s["corta"] if s else item["k"]),
        })

    claustros = [{"k": i["k"], "n": i["n"], "etq": etiquetas.get(i["k"], i["k"])}
                 for i in contar(registros, "claustro")]
    roles = [{"k": i["k"], "n": i["n"], "etq": etiquetas.get(i["k"], i["k"])}
             for i in contar(registros, "rol")]

    recientes = []
    for r in registros[-60:]:
        s = SEDES["nodos"].get(r["unidad"])
        recientes.append({
            "i": r["i"], "hora": r["hora"],
            "unidad": r["unidad_cruda"] or r["unidad"],
            "corta": s["corta"] if s else "Sin ubicación",
            "tipo": s["tipo"] if s else "otro",
            "claustro": etiquetas.get(r["claustro"], r["claustro"]),
            "rol": etiquetas.get(r["rol"], r["rol"]),
        })

    ultimo_pulso = recientes[-1]["i"] if recientes else -1
    return {
        "ok": error is None,
        "modo": modo,
        "error": error,
        "ts": ahora().strftime("%H:%M:%S"),
        "ts_epoch": ahora_ts,
        "version": version,
        "total": len(registros),
        "en_mapa": sum(1 for r in registros if r["unidad"] != "Otro"),
        "sin_ubicacion": sum(1 for r in registros if r["unidad"] == "Otro"),
        "sedes_activas": len({r["unidad"] for r in registros if r["unidad"] != "Otro"}),
        "ultima_hora": registros[-1]["hora"] if registros else "--:--:--",
        "unidades": unidades,
        "claustros": claustros,
        "roles": roles,
        "recientes": recientes,
        "ultimo_pulso": ultimo_pulso,
        "vida_pulso_s": vida,
        "arranque_epoch": t0,
    }


# --------------------------------------------------------------------- estado compartido
class Estado:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.lock = threading.Lock()
        self.registros: list[dict] = []
        self.version = 0
        self.hash = ""
        self.error: str | None = None
        self.modo = "esperando"
        self.t0 = time.time()
        self.ultimo_refresco = 0.0

    def refrescar(self, forzar=False):
        cfg = self.cfg
        f = cfg["frecuencia"]["servidor_s"]
        if not forzar and time.time() - self.ultimo_refresco < f:
            return
        self.ultimo_refresco = time.time()
        try:
            filas, modo = obtener_filas(cfg)
            regs = normalizar(filas, cfg)
            h = hashlib.sha1(json.dumps(
                [(r["unidad"], r["claustro"], r["rol"], r["hora"]) for r in regs],
                ensure_ascii=False).encode()).hexdigest()
            with self.lock:
                self.registros = regs
                self.modo = modo
                self.error = None
                if h != self.hash:
                    self.hash = h
                    self.version += 1
        except Exception as e:  # se conserva el último snapshot bueno
            with self.lock:
                self.error = f"{type(e).__name__}: {e}"

    def retrato(self) -> dict:
        with self.lock:
            return snapshot(self.registros, self.cfg, self.modo, self.error,
                            self.version, self.t0)


def obtener_filas(cfg: dict):
    p = cfg["planilla"]
    if cfg.get("demo", {}).get("activo"):
        d = cfg["demo"]
        transcurrido = time.time() - T0_DEMO
        n = min(int(d.get("total", 260)),
                int(d.get("arranque", 12)) + int(max(0.0, transcurrido) / max(0.2, float(d.get("ritmo_s", 4.0)))))
        return filas_demo(cfg, n), "demo"
    if p.get("csv_local"):
        ruta = p["csv_local"]
        if not os.path.isabs(ruta):
            ruta = os.path.join(AQUI, ruta)
        return leer_csv(ruta), "csv"
    if p.get("id"):
        return leer_sheet(p["id"], p.get("hoja", ""), p.get("rango", "A1:F")), "planilla"
    # sin fuente configurada: demo automática (así el tablero nunca queda vacío)
    cfg["demo"]["activo"] = True
    return filas_demo(cfg, int(cfg["demo"].get("arranque", 12))), "demo"


# --------------------------------------------------------------------- HTTP
class Handler(SimpleHTTPRequestHandler):
    estado: Estado = None
    cfg: dict = None

    def __init__(self, *a, **kw):
        super().__init__(*a, directory=WEB, **kw)

    def log_message(self, fmt, *args):
        if "/api/" not in (self.path or ""):
            sys.stderr.write("  · %s\n" % (fmt % args))

    def _json(self, obj, code=200):
        cuerpo = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.end_headers()
        self.wfile.write(cuerpo)

    def do_GET(self):
        ruta = self.path.split("?")[0]
        if ruta == "/api/estado":
            self.estado.refrescar()
            d = self.estado.retrato()
            d["cfg"] = {
                "evento": self.cfg["evento"],
                "cliente_s": self.cfg["frecuencia"]["cliente_s"],
                "etiquetas_unidad": self.cfg.get("etiquetas_unidad", {}),
                "mapa": self.cfg.get("mapa", {}),
            }
            self._json(d)
            return
        if ruta == "/api/salud":
            self._json({"ok": self.estado.error is None,
                        "modo": self.estado.modo,
                        "version": self.estado.version,
                        "error": self.estado.error})
            return
        if ruta == "/":
            self.path = "/index.html"
        return super().do_GET()

    def end_headers(self):
        if not self.path.startswith("/api/"):
            self.send_header("Cache-Control", "no-store, max-age=0")
        super().end_headers()


# --------------------------------------------------------------------- main
SEDES: dict = {}


def main():
    global SEDES
    ap = argparse.ArgumentParser(description="Tablero en vivo PDI 2026")
    ap.add_argument("--demo", action="store_true", help="datos simulados, sin red")
    ap.add_argument("--csv", metavar="ARCHIVO", help="respuestas en CSV local")
    ap.add_argument("--sheet", metavar="ID", help="ID de la planilla de respuestas")
    ap.add_argument("--hoja", metavar="NOMBRE", help="nombre de la pestaña")
    ap.add_argument("--puerto", type=int, default=8770)
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--ritmo", type=float, help="segundos entre ingresos simulados (demo)")
    ap.add_argument("--total", type=int, help="total de asistentes simulados (demo)")
    ap.add_argument("--imprimir", action="store_true", help="imprime el snapshot y sale")
    ap.add_argument("--exportar", metavar="RUTA", help="escribe el snapshot JSON en RUTA "
                    "(para el sitio estático: --exportar web/data/estado.json)")
    ap.add_argument("--cada", type=float, default=0.0,
                    help="con --exportar: reescribe el snapshot cada N segundos (0 = una sola vez)")
    args = ap.parse_args()

    cfg = cargar_config()
    SEDES = cargar_sedes()
    if args.csv:
        cfg["planilla"]["csv_local"] = args.csv
        cfg["planilla"]["id"] = ""
        cfg["demo"]["activo"] = False
    if args.sheet:
        cfg["planilla"]["id"] = args.sheet
        cfg["planilla"]["csv_local"] = ""
        cfg["demo"]["activo"] = False
    if args.hoja:
        cfg["planilla"]["hoja"] = args.hoja
    if args.ritmo:
        cfg["demo"]["ritmo_s"] = args.ritmo
    if args.total:
        cfg["demo"]["total"] = args.total
    # sin planilla ni CSV -> demo
    if args.demo or (not cfg["planilla"].get("id") and not cfg["planilla"].get("csv_local")):
        cfg["demo"]["activo"] = True
    cfg["demo"].setdefault("arranque", 12)

    estado = Estado(cfg)
    estado.t0 = time.time()
    if args.imprimir:
        estado.refrescar(forzar=True)
        print(json.dumps(estado.retrato(), ensure_ascii=False, indent=1))
        return

    if args.exportar:
        # hornea el snapshot que consume el sitio estático (?fuente=json),
        # sin necesidad de backend ni de exponer credenciales en el navegador
        ruta = args.exportar if os.path.isabs(args.exportar) else os.path.join(AQUI, args.exportar)
        carpeta = os.path.dirname(ruta)
        if carpeta:
            os.makedirs(carpeta, exist_ok=True)

        def escribir():
            estado.refrescar(forzar=True)
            d = estado.retrato()
            d["cfg"] = {"evento": cfg["evento"],
                        "cliente_s": cfg["frecuencia"]["cliente_s"],
                        "etiquetas_unidad": cfg.get("etiquetas_unidad", {}),
                        "mapa": cfg.get("mapa", {})}
            d["fuente"] = "json"
            tmp = ruta + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(d, f, ensure_ascii=False, indent=1)
            os.replace(tmp, ruta)
            print(f"  snapshot -> {ruta}  ({d['total']} registros, modo {d['modo']}, {d['ts']})")

        escribir()
        if args.cada and args.cada > 0:
            try:
                while True:
                    time.sleep(max(2.0, args.cada))
                    escribir()
            except KeyboardInterrupt:
                pass
        return

    Handler.estado = estado
    Handler.cfg = cfg

    def bombeo():
        while True:
            estado.refrescar(forzar=True)
            time.sleep(max(1.0, cfg["frecuencia"]["servidor_s"]))

    threading.Thread(target=bombeo, daemon=True).start()
    time.sleep(0.4)

    fuente = ("DEMO (datos simulados)" if cfg["demo"]["activo"] else
              f"CSV {cfg['planilla']['csv_local']}" if cfg["planilla"].get("csv_local") else
              f"planilla {cfg['planilla']['id']}")
    print(f"\n  Tablero PDI 2026  ·  fuente: {fuente}")
    print(f"  refresco servidor {cfg['frecuencia']['servidor_s']}s · cliente {cfg['frecuencia']['cliente_s']}s")
    print(f"  →  http://localhost:{args.puerto}/   (pantalla completa: F11)\n")
    ThreadingHTTPServer((args.host, args.puerto), Handler).serve_forever()


if __name__ == "__main__":
    main()