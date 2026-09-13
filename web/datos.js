/* ============================================================================
   datos.js · capa de datos del tablero PDI 2026 · Universidad Provincial de Córdoba

   Puerto a JavaScript de la lógica de server.py, para que el tablero funcione
   como sitio 100% estático (GitHub Pages no ejecuta Python).

   Fuentes soportadas (?fuente=... en la URL, o config.fuente.modo):
     api   → Google Sheets API v4 con API key (hoja pública, sin caché, en vivo)
     csv   → planilla pública exportada como CSV (sin API key, ~1 min de retraso)
     json  → snapshot ya agregado en data/estado.json (lo hornea server.py --exportar)
     auto  → api/estado del servidor local si existe → api → csv → json → demo
     demo  → datos simulados deterministas (no requiere red ni planilla)

   Nunca lanza por problemas de fuente: devuelve un snapshot con ok:false y el
   motivo en .error, conservando el último dato válido si hay algo guardado.
   ========================================================================== */
'use strict';

const Datos = (() => {

  const CLAVES = ['hora', 'correo', 'unidad', 'claustro', 'rol'];
  const CLAVES_BUSQUEDA = ['marca temporal', 'correo', 'unidad', 'claustro', 'rol'];
  const CACHE_KEY = 'pdi2026.ultimo';

  let CFG = null;          // config.json (web/data/config.json)
  let SEDES = null;        // data/sedes.json
  let T0 = null;           // arranque del tablero (epoch ms)
  let T0_DEMO = null;      // arranque del generador demo
  let version = 0;
  let hashPrev = '';

  /* ─────────────────────────── normalización de texto ─────────────────────── */
  const sinAcentos = s => String(s === null || s === undefined ? '' : s)
    .normalize('NFD').replace(/[\u0300-\u036f]/g, '');
  // El guion se normaliza: en el formulario las sedes vienen como
  // "Sede Regional Bell Ville-Mariano Moreno" (sin espacios), así que "a - b" y
  // "a-b" tienen que compararse igual y hacer match exacto igual.
  const norm = s => sinAcentos(s).replace(/\s*-\s*/g, '-').replace(/\s+/g, ' ').trim().toLowerCase();
  const limpiar = s => String(s === null || s === undefined ? '' : s).replace(/\s+/g, ' ').trim();

  const dos = n => String(n).padStart(2, '0');
  const hhmmss = d => dos(d.getHours()) + ':' + dos(d.getMinutes()) + ':' + dos(d.getSeconds());

  /* ─────────────────────────── carga de recursos ──────────────────────────── */
  async function cargarConfig() {
    if (CFG) return CFG;
    const r = await fetch('data/config.json', { cache: 'no-store' });
    if (!r.ok) throw new Error('no se pudo leer data/config.json (HTTP ' + r.status + ')');
    CFG = await r.json();
    return CFG;
  }

  async function cargarSedes() {
    if (SEDES) return SEDES;
    const r = await fetch('data/sedes.json', { cache: 'no-store' });
    if (!r.ok) throw new Error('no se pudo leer data/sedes.json (HTTP ' + r.status + ')');
    SEDES = await r.json();
    return SEDES;
  }

  /* ─────────────────────────── normalización de filas ─────────────────────── */
  // Ubica cada columna por palabra clave del encabezado; si no hay encabezado usa
  // el orden declarado en config.planilla.orden (o el orden del formulario).
  function mapearColumnas(encabezado, cfg, orden) {
    const reglas = (cfg.planilla && cfg.planilla.columnas) || {};
    const idx = {};
    const enc = (encabezado || []).map(norm);
    Object.keys(reglas).forEach(clave => {
      for (let j = 0; j < enc.length; j++) {
        if (reglas[clave].some(p => enc[j].includes(norm(p)))) { idx[clave] = j; break; }
      }
    });
    const fallback = orden || (cfg.planilla && cfg.planilla.orden) || CLAVES;
    fallback.forEach((k, pos) => { if (idx[k] === undefined) idx[k] = pos; });
    return idx;
  }

  function ubicarUnidad(valor, cfg) {
    const v = norm(valor);
    if (!v) return 'Otro';
    const nodos = Object.keys(SEDES.nodos);
    for (const canonica of nodos) if (norm(canonica) === v) return canonica;
    const mapeo = cfg.mapeo_unidad || {};
    for (const clave of Object.keys(mapeo)) if (v.includes(norm(clave))) return mapeo[clave];
    return 'Otro';
  }

  function canonizarClaustro(valor) {
    const v = norm(valor);
    for (const c of ['Docente', 'Estudiantil', 'No docente', 'Graduados']) if (norm(c) === v) return c;
    if (v.includes('no docente')) return 'No docente';
    if (v.includes('estudiant')) return 'Estudiantil';
    if (v.includes('graduad')) return 'Graduados';
    if (v.includes('docente')) return 'Docente';
    return 'Sin dato';
  }

  function canonizarRol(valor, cfg) {
    const v = norm(valor);
    if (!v) return 'Sin dato';
    for (const [frag, canonico] of (cfg.reglas_rol || [])) if (v.includes(norm(frag))) return canonico;
    return 'Otro';
  }

  function parsearHora(txt) {
    const t = limpiar(txt);
    if (!t) return null;
    let m = t.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})[ T](\d{1,2}):(\d{2})(?::(\d{2}))?/);
    if (m) return new Date(+m[3], +m[2] - 1, +m[1], +m[4], +m[5], +(m[6] || 0));
    m = t.match(/^(\d{4})-(\d{2})-(\d{2})[ T](\d{1,2}):(\d{2})(?::(\d{2}))?/);
    if (m) return new Date(+m[1], +m[2] - 1, +m[3], +m[4], +m[5], +(m[6] || 0));
    const d = new Date(t);
    return isNaN(d.getTime()) ? null : d;
  }

  function normalizar(filas, cfg, orden) {
    if (!filas || !filas.length) return [];
    const primera = norm(filas[0].map(c => String(c === null || c === undefined ? '' : c)).join(' '));
    const esEncabezado = CLAVES_BUSQUEDA.some(p => primera.includes(norm(p)));
    const idx = mapearColumnas(esEncabezado ? filas[0] : [], cfg, orden);
    const cuerpo = esEncabezado ? filas.slice(1) : filas;

    const regs = [];
    cuerpo.forEach(fila => {
      if (!fila.some(c => limpiar(c))) return;
      const celda = k => { const j = idx[k]; return j < fila.length ? limpiar(fila[j]) : ''; };
      const cruda = celda('unidad');
      const t = parsearHora(celda('hora'));
      regs.push({
        i: regs.length,
        hora: t ? hhmmss(t) : celda('hora').slice(0, 8),
        hora_iso: t ? t.toISOString() : null,
        clave_hora: t ? t.getTime() : 0,
        unidad: ubicarUnidad(cruda, cfg),
        unidad_cruda: cruda,
        claustro: canonizarClaustro(celda('claustro')),
        rol: canonizarRol(celda('rol'), cfg),
      });
    });
    regs.sort((a, b) => (a.clave_hora - b.clave_hora) || (a.i - b.i));
    regs.forEach((r, k) => { r.i = k; });
    return regs;
  }

  /* ─────────────────────────── agregación ─────────────────────────────────── */
  function contar(regs, campo) {
    const c = new Map();
    regs.forEach(r => c.set(r[campo], (c.get(r[campo]) || 0) + 1));
    return [...c.entries()]
      .map(([k, n]) => ({ k, n }))
      .sort((a, b) => (b.n - a.n) || a.k.localeCompare(b.k, 'es'));
  }

  function snapshot(regs, cfg, modo, error) {
    const etq = cfg.etiquetas || {};
    const frec = cfg.frecuencia || {};
    const nodos = (SEDES && SEDES.nodos) || {};

    const unidades = contar(regs, 'unidad').map(it => {
      const s = nodos[it.k];
      return {
        k: it.k, n: it.n,
        lat: s ? s.lat : null, lon: s ? s.lon : null,
        dep: s ? s.dep : null, tipo: s ? s.tipo : 'otro',
        corta: s ? s.corta : it.k,
      };
    });

    const conEtq = items => items.map(i => ({ k: i.k, n: i.n, etq: etq[i.k] || i.k }));

    const recientes = regs.slice(-60).map(r => {
      const s = nodos[r.unidad];
      return {
        i: r.i, hora: r.hora,
        unidad: r.unidad_cruda || r.unidad,
        corta: s ? s.corta : 'Sin ubicación',
        tipo: s ? s.tipo : 'otro',
        claustro: etq[r.claustro] || r.claustro,
        rol: etq[r.rol] || r.rol,
      };
    });

    const huella = JSON.stringify(regs.map(r => [r.unidad, r.claustro, r.rol, r.hora]));
    if (huella !== hashPrev) { hashPrev = huella; version++; }

    const ahora = new Date();
    return {
      ok: error === null || error === undefined,
      modo: modo,
      error: error || null,
      ts: hhmmss(ahora),
      ts_epoch: ahora.getTime(),
      version: version,
      total: regs.length,
      en_mapa: regs.filter(r => r.unidad !== 'Otro').length,
      sin_ubicacion: regs.filter(r => r.unidad === 'Otro').length,
      sedes_activas: new Set(regs.filter(r => r.unidad !== 'Otro').map(r => r.unidad)).size,
      sedes_regionales: (() => {
        const s = new Set();
        regs.forEach(r => { const n = nodos[r.unidad]; if (n && n.tipo === 'sede') s.add(r.unidad); });
        return s.size;
      })(),
      ultima_hora: regs.length ? regs[regs.length - 1].hora : '--:--:--',
      unidades: unidades,
      claustros: conEtq(contar(regs, 'claustro')),
      roles: conEtq(contar(regs, 'rol')),
      recientes: recientes,
      ultimo_pulso: recientes.length ? recientes[recientes.length - 1].i : -1,
      vida_pulso_s: frec.vida_pulso_s || 90,
      arranque_epoch: T0,
      cfg: {
        evento: cfg.evento || {},
        cliente_s: frec.cliente_s || 3,
        mapa: cfg.mapa || {},
        etiquetas_unidad: cfg.etiquetas_unidad || {},
        colores_unidad: cfg.colores_unidad || {},
        grupos: cfg.grupos || [],
      },
    };
  }

  /* ─────────────────────────── CSV ─────────────────────────────────────────── */
  function parseCSV(texto, delim) {
    const filas = [];
    let fila = [], campo = '', comillas = false;
    const d = delim || ',';
    for (let i = 0; i < texto.length; i++) {
      const c = texto[i];
      if (comillas) {
        if (c === '"') { if (texto[i + 1] === '"') { campo += '"'; i++; } else comillas = false; }
        else campo += c;
      } else if (c === '"') comillas = true;
      else if (c === d) { fila.push(campo); campo = ''; }
      else if (c === '\n') { fila.push(campo); filas.push(fila); fila = []; campo = ''; }
      else if (c !== '\r') campo += c;
    }
    if (campo !== '' || fila.length) { fila.push(campo); filas.push(fila); }
    return filas;
  }

  /* ─────────────────────────── fuentes ─────────────────────────────────────── */
  const urlSheets = (id, rangos, hoja, key) => {
    const pre = hoja ? hoja + '!' : '';
    const q = rangos.map(r => 'ranges=' + encodeURIComponent(pre + r)).join('&');
    return `https://sheets.googleapis.com/v4/spreadsheets/${id}/values:batchGet?${q}` +
           `&majorDimension=ROWS&key=${encodeURIComponent(key)}`;
  };

  // Lee solo las columnas necesarias (por defecto deja afuera la de correos).
  async function fuenteApi(cfg) {
    const p = cfg.planilla || {}, f = cfg.fuente || {};
    if (!p.id) throw new Error('falta planilla.id en la configuración');
    if (!f.api_key) throw new Error('falta fuente.api_key (API key de Google Cloud)');
    const rangos = p.rangos_sin_correo || ['A1:A', 'C1:F'];
    const r = await fetch(urlSheets(p.id, rangos, p.hoja || '', f.api_key), { cache: 'no-store' });
    if (!r.ok) {
      const t = await r.text().catch(() => '');
      throw new Error('Sheets API HTTP ' + r.status + ' ' + t.slice(0, 140));
    }
    const d = await r.json();
    const partes = (d.valueRanges || []).map(v => v.values || []);
    const n = Math.max(0, ...partes.map(a => a.length));
    const filas = [];
    for (let i = 0; i < n; i++) {
      const fila = [];
      partes.forEach(a => (a[i] || []).forEach(c => fila.push(c)));
      filas.push(fila);
    }
    return { filas, orden: ['hora', 'unidad', 'claustro', 'rol'] };
  }

  async function fuenteCsv(cfg) {
    const p = cfg.planilla || {}, f = cfg.fuente || {};
    let url = f.csv_url;
    if (!url && p.csv_url) url = p.csv_url;
    if (!url && p.id) {
      url = `https://docs.google.com/spreadsheets/d/${p.id}/export?format=csv` +
            (p.gid ? `&gid=${encodeURIComponent(p.gid)}` : '');
    }
    if (!url) throw new Error('falta fuente.csv_url (o planilla.id) para leer el CSV');
    const sep = url.includes('?') ? '&' : '?';
    const r = await fetch(url + sep + '_=' + Date.now(), { cache: 'no-store' });
    if (!r.ok) throw new Error('CSV HTTP ' + r.status);
    const texto = await r.text();
    if (/^\s*<(!doctype|html)/i.test(texto)) {
      throw new Error('el CSV devolvió HTML: la planilla no es pública (compartir como "cualquier persona con el enlace")');
    }
    const primera = texto.slice(0, 4000);
    const delim = (primera.match(/;/g) || []).length > (primera.match(/,/g) || []).length ? ';' : ',';
    return { filas: parseCSV(texto, delim) };
  }

  async function fuenteJson(cfg, ruta) {
    const camino = ruta || (cfg.fuente && cfg.fuente.json_local) || 'data/estado.json';
    const r = await fetch(camino + (camino.includes('?') ? '&' : '?') + 'v=' + Date.now(), { cache: 'no-store' });
    if (!r.ok) throw new Error('snapshot HTTP ' + r.status + ' (' + camino + ')');
    const d = await r.json();
    if (!d || typeof d.total !== 'number' || !Array.isArray(d.unidades)) {
      throw new Error('el snapshot no tiene el formato esperado (' + camino + ')');
    }
    return { listo: d };
  }

  /* ─────────────────────────── generador demo ─────────────────────────────── */
  function azar(semilla) {                       // mulberry32, determinista
    let a = (semilla >>> 0) || 2026;
    return () => {
      a = (a + 0x6D2B79F5) >>> 0;
      let t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  function filasDemo(cfg, n) {
    const d = cfg.demo || {};
    const rnd = azar(d.semilla || 2026);
    const nodos = SEDES.nodos;
    const sedes = Object.keys(nodos).filter(k => nodos[k].tipo === 'sede');
    const internas = Object.keys(nodos).filter(k => nodos[k].tipo !== 'sede');
    const pesoCapital = d.peso_capital === undefined ? 0.52 : d.peso_capital;
    const claustros = [['Docente', 0.46], ['No docente', 0.24], ['Estudiantil', 0.20], ['Graduados', 0.10]];
    const roles = {
      'Docente': [['Docente', .66], ['Dirección o Coordinación de carrera', .14],
                  ['Dirección o Coordinación de área', .10], ['Autoridad institucional', .04],
                  ['Secretaria o Secretario', .06]],
      'No docente': [['Personal no docente', .74], ['Dirección o Coordinación de área', .13],
                     ['Secretaria o Secretario', .08], ['Autoridad institucional', .05]],
      'Estudiantil': [['Estudiante de pregrado y/o grado', .82], ['Estudiante de posgrado', .18]],
      'Graduados': [['Graduado', .86], ['Docente', .14]],
    };
    const elegir = pares => {
      const r = rnd(); let acc = 0;
      for (const [v, p] of pares) { acc += p; if (r <= acc) return v; }
      return pares[pares.length - 1][0];
    };
    const ritmo = (d.ritmo_s || 4) * 1000;
    const filas = [];
    for (let i = 0; i < n; i++) {
      const unidad = rnd() < pesoCapital ? internas[Math.floor(rnd() * internas.length)]
                                         : sedes[Math.floor(rnd() * sedes.length)];
      const claustro = elegir(claustros);
      const rol = elegir(roles[claustro]);
      const t = new Date(T0_DEMO + i * ritmo);
      filas.push([`${dos(t.getDate())}/${dos(t.getMonth() + 1)}/${t.getFullYear()} ${hhmmss(t)}`,
                  'asistente' + String(i + 1).padStart(3, '0') + '@upc.edu.ar',
                  unidad, claustro, rol]);
    }
    return filas;
  }

  function fuenteDemo(cfg) {
    if (T0_DEMO === null) T0_DEMO = Date.now();
    const d = cfg.demo || {};
    const total = d.total || 260, arranque = d.arranque || 12, ritmo = d.ritmo_s || 4;
    const transcurrido = (Date.now() - T0_DEMO) / 1000;
    const n = Math.min(total, Math.round(arranque + Math.max(0, transcurrido) / Math.max(0.2, ritmo)));
    return { filas: filasDemo(cfg, n) };
  }

  /* ─────────────────────────── último snapshot válido ─────────────────────── */
  function recordar(d) {
    try { localStorage.setItem(CACHE_KEY, JSON.stringify({ t: Date.now(), d })); } catch (e) { /* modo privado */ }
  }
  function recordado() {
    try {
      const x = JSON.parse(localStorage.getItem(CACHE_KEY) || 'null');
      if (x && x.d && Date.now() - x.t < 12 * 3600e3) return x.d;
    } catch (e) { /* ignore */ }
    return null;
  }

  /* ─────────────────────────── plan de fuentes ─────────────────────────────── */
  function plan(cfg, pedido) {
    const p = cfg.planilla || {}, f = cfg.fuente || {};
    const hayPlanilla = !!(p.id || p.csv_url || f.csv_url);
    const pasos = [];
    if (pedido === 'demo') return ['demo'];
    if (pedido === 'api')  return ['api'];
    if (pedido === 'csv')  return ['csv'];
    if (pedido === 'json') return ['json'];
    if (pedido === 'auto') {
      pasos.push('servidor');                    // server.py local (/api/estado)
      if (hayPlanilla && f.api_key) pasos.push('api');
      if (hayPlanilla) pasos.push('csv');
      pasos.push('json');
      if (!pasos.includes('demo')) pasos.push('demo');
      return pasos;
    }
    return ['servidor', 'api', 'csv', 'json', 'demo'];
  }

  async function desdeServidor() {
    const r = await fetch('api/estado', { cache: 'no-store' });
    if (!r.ok) throw new Error('servidor local HTTP ' + r.status);
    const d = await r.json();
    if (!d || typeof d.total !== 'number') throw new Error('respuesta del servidor inesperada');
    return { listo: d };
  }

  /* ─────────────────────────── API pública ─────────────────────────────────── */
  async function leerEstado() {
    const cfg = await cargarConfig();
    await cargarSedes();
    if (T0 === null) T0 = Date.now();

    const sp = new URLSearchParams(location.search);
    const pedido = sp.get('demo') ? 'demo' : (sp.get('fuente') || (cfg.fuente && cfg.fuente.modo) || 'auto');
    const urlForzada = sp.get('url');          // ?fuente=csv&url=... (probar otra planilla/CSV)
    if (urlForzada) cfg.fuente = Object.assign({}, cfg.fuente, { csv_url: urlForzada });
    const errores = [];

    for (const paso of plan(cfg, pedido)) {
      try {
        let listo = null, filas = null, orden = null;
        if (paso === 'servidor') ({ listo } = await desdeServidor());
        else if (paso === 'api') ({ filas, orden } = await fuenteApi(cfg));
        else if (paso === 'csv') ({ filas } = await fuenteCsv(cfg));
        else if (paso === 'json') ({ listo } = await fuenteJson(cfg));
        else if (paso === 'demo') ({ filas } = await fuenteDemo(cfg));

        if (filas) listo = snapshot(normalizar(filas, cfg, orden), cfg, paso === 'demo' ? 'demo' : paso, null);

        if (listo) {
          const aviso = errores.length ? 'se usó ' + paso + ' tras fallar: ' + errores.join(' | ') : null;
          listo.modo = paso === 'json' ? 'archivo' : listo.modo;
          listo.ok = true;
          listo.error = aviso;
          // fuente real del dato: en modo servidor el snapshot ya trae su propio modo
          listo.fuente = paso === 'servidor' ? (listo.modo || 'servidor') : paso;
          listo.pasos_fallidos = errores.slice();
          recordar(listo);
          return listo;
        }
      } catch (e) {
        errores.push(paso + ': ' + (e && e.message ? e.message : e));
      }
    }

    // Ninguna fuente respondió: se muestra el último dato válido, avisando el fallo.
    const previo = recordado();
    if (previo) {
      previo.ok = false;
      previo.error = errores.join(' | ');
      previo.modo = 'sin-conexion';
      return previo;
    }
    return snapshot([], cfg, 'esperando', errores.join(' | '));
  }

  return { leerEstado, cargarConfig, cargarSedes, normalizar, snapshot, parseCSV };
})();
