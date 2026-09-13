/* ============================================================================
   Tablero en vivo · PDI 2026 · Universidad Provincial de Córdoba
   - Pide el snapshot a datos.js (Google Sheet / CSV / snapshot / demo / servidor local).
   - Detecta los ingresos nuevos y los muestra con ondas tipo sonar en el mapa.
   - Gráficos en SVG generados a mano (sin librerías, sin CDN: funciona offline).
   ========================================================================== */
'use strict';

const $  = s => document.querySelector(s);
const NS = 'http://www.w3.org/2000/svg';

/* ───────────────────────── proyección del mapa ─────────────────────────
   viewBox 430×624: la provincia de Córdoba es vertical (~358×584 dentro del
   viewBox), por eso el mapa va centrado y las tarjetas lo flanquean.        */
const M = { prov:null, proy:null,
  W:430, H:624, margen:10,
  anillos:[], nodos:new Map(), cfgMapa:{} };

/* ───────────────────────── estado del tablero ──────────────────── */
const S = {
  cfg:null, prev:new Map(), ultimoVisto:-1,
  totalPrev:0, primera:true, fallos:0, modo:'',
};

/* ══════════════════════ arranque ══════════════════════ */
escalar();
window.addEventListener('resize', escalar);

function escalar(){
  const e = Math.min(window.innerWidth / 1920, window.innerHeight / 1080);
  document.documentElement.style.setProperty('--esc', e.toFixed(4));
}

reloj();
setInterval(reloj, 1000);
animar();
cargar();

function reloj(){
  $('#reloj').textContent = new Date().toLocaleTimeString('es-AR', {hour12:false});
}

/* ══════════════════════ datos ══════════════════════
   Toda la lectura/normalización vive en datos.js (100% cliente, apto GitHub
   Pages). Devuelve un snapshot con el mismo formato que /api/estado. */
let intervalo = null;

async function cargar(){
  let d;
  try{
    d = await Datos.leerEstado();
    if(!d) throw new Error('sin datos');
    S.fallos = 0;
  }catch(err){
    S.fallos++;
    pintarEstado(false, 'Sin conexión · reintentando (' + S.fallos + '): ' +
                        (err && err.message ? err.message : err));
    return;
  }

  if(S.cfg === null){
    S.cfg = d.cfg || {};
    M.cfgMapa = (S.cfg.mapa || {});
    pintarCabecera(d.cfg || {});
    if(M.prov) pintarMapaBase();
    const cada = Math.max(2, (S.cfg.cliente_s || 3)) * 1000;
    intervalo = setInterval(cargar, cada);
  }

  pintarEstado(d.ok, d);

  if(d.total !== S.totalPrev){
    const n = $('#total');
    n.textContent = d.total;
    n.classList.add('sube');
    setTimeout(()=>n.classList.remove('sube'), 700);
    S.totalPrev = d.total;
  }

  pintarTorta(d.claustros, d.total);
  pintarBarras(d.roles);
  pintarUnidades(d.unidades);
  pintarGrupos(d.unidades);
  pintarSedes(d.unidades);
  pintarMapa(d.unidades);
  pintarUltimos(d.recientes);
  pintarKpis(d);

  $('#pie-actualizado').textContent =
    'Último ingreso ' + d.ultima_hora + ' · actualizado ' + d.ts;
  S.modo = d.modo;
}

function pintarCabecera(cfg){
  const ev = cfg.evento || {};
  if(ev.titulo)    $('#titulo').textContent = ev.titulo;
  if(ev.subtitulo) $('#subtitulo').textContent = ev.subtitulo;
  if(ev.fuente)    $('#pie-fuente').textContent = 'Fuente: ' + ev.fuente;
  $('#pie-estado').dataset.base = 'Lectura cada ' + (cfg.cliente_s || 3) + ' s';
}

const ETIQUETA_MODO = {'demo':'DEMO', 'archivo':'ARCHIVO', 'sin-conexion':'SIN DATOS',
                        'esperando':'ESPERANDO', 'csv':'EN VIVO', 'api':'EN VIVO',
                        'planilla':'EN VIVO', 'servidor':'EN VIVO'};

function pintarEstado(ok, d){
  const p = $('#punto'), t = $('#estado-txt'), est = $('#pie-estado');
  const modo = (d && d.modo) || 'servidor';
  if(ok){
    p.classList.remove('off');
    t.textContent = ETIQUETA_MODO[modo] || 'EN VIVO';
    est.classList.remove('alerta');
    const base = $('#pie-estado').dataset.base || 'Lectura cada 3 s';
    // si no hay planilla indicada, se avisa cómo indicarla (salvo en modo demo)
    const falta = (S.cfg && S.cfg.sin_planilla && modo !== 'demo')
      ? ' · falta la planilla: agregá ?planilla=<id>' : '';
    est.textContent = base + ' · últ. lectura ' + d.ts +
                      (modo === 'demo' ? ' · datos simulados' : '') +
                      (modo === 'archivo' ? ' · snapshot, no es lectura en vivo' : '') +
                      falta;
  }else{
    p.classList.add('off');
    t.textContent = 'SIN DATOS';
    est.classList.add('alerta');
    est.textContent = 'No se pudo leer la fuente: ' + (typeof d === 'string' ? d : (d.error || 'desconocido')) +
                      ' · se conserva el último dato válido';
  }
}

function pintarKpis(d){
  $('#kpi-sedes').textContent = (d.sedes_regionales === undefined ? d.sedes_activas : d.sedes_regionales);
  $('#kpi-mapa').textContent  = d.en_mapa;
  const otro = $('#mini-otro');
  $('#kpi-otro').textContent = d.sin_ubicacion;
  otro.hidden = d.sin_ubicacion === 0;
  $('#mapa-total').textContent  = d.en_mapa + ' de ' + d.total + ' ubicados';
  $('#claustro-total').textContent = d.total + ' respuestas';
  $('#rol-total').textContent = d.total + ' respuestas';
  $('#unidades-total').textContent = d.unidades.length + ' dependencias';
}

/* ══════════════════════ torta: claustro ══════════════════════ */
const AMARILLOS = ['#F7A600', '#1A1A1A', '#FFC24D', '#8E8E8E', '#E8A200'];

function pintarTorta(items, total){
  const svg = $('#torta');
  const orden = (items || []).slice();
  const otros = orden.filter(o => o.k === 'Sin dato');
  const vis = orden.filter(o => o.k !== 'Sin dato');
  const datos = vis.concat(otros);
  const suma = datos.reduce((a,b)=> a + b.n, 0) || 1;

  const cx = 210, cy = 190, r1 = 132, r2 = 76;
  let a0 = -Math.PI/2;
  let html = '';

  datos.forEach((it, i) => {
    const frac = it.n / suma;
    const a1 = a0 + frac * Math.PI * 2;
    const col = AMARILLOS[i % AMARILLOS.length];
    if(it.n > 0){
      html += `<path d="${arco(cx,cy,r1,r2,a0,a1)}" fill="${col}"
                 stroke="#FFFFFF" stroke-width="2.5"/>`;
    }
    a0 = a1;
  });

  html += `<circle cx="${cx}" cy="${cy}" r="${r2 - 2}" fill="#FFFFFF"/>`;
  html += `<text x="${cx}" y="${cy - 6}" text-anchor="middle"
             font-family="JetBrains Mono, monospace" font-size="52" font-weight="700"
             fill="#111111">${total}</text>`;
  html += `<text x="${cx}" y="${cy + 22}" text-anchor="middle"
             font-family="JetBrains Mono, monospace" font-size="13" letter-spacing="1"
             fill="#6E6E6E">ASISTENTES</text>`;
  svg.innerHTML = html;

  const ley = document.createElement('div');
  ley.className = 'leyenda';
  datos.forEach((it, i) => {
    const pct = Math.round(100 * it.n / suma);
    ley.insertAdjacentHTML('beforeend', `
      <div class="leyenda-item">
        <i class="leyenda-sim" style="background:${AMARILLOS[i % AMARILLOS.length]}"></i>
        <span class="leyenda-nom">${esc(it.etq || it.k)}</span>
        <span class="leyenda-val">${it.n}<small>${pct}%</small></span>
      </div>`);
  });
  const cont = svg.parentElement;
  const vieja = cont.querySelector('.leyenda');
  if(vieja) vieja.remove();
  cont.appendChild(ley);
}

function arco(cx, cy, r1, r2, a0, a1){
  const grande = (a1 - a0) > Math.PI ? 1 : 0;
  const x = (r,a) => (cx + r*Math.cos(a)).toFixed(2);
  const y = (r,a) => (cy + r*Math.sin(a)).toFixed(2);
  if((a1 - a0) >= Math.PI*2 - 0.0001){   // círculo completo: dos mitades
    return `M ${cx} ${cy-r1} A ${r1} ${r1} 0 1 1 ${cx} ${cy+r1} A ${r1} ${r1} 0 1 1 ${cx} ${cy-r1} Z
            M ${cx} ${cy-r2} A ${r2} ${r2} 0 1 0 ${cx} ${cy+r2} A ${r2} ${r2} 0 1 0 ${cx} ${cy-r2} Z`;
  }
  return `M ${x(r1,a0)} ${y(r1,a0)} A ${r1} ${r1} 0 ${grande} 1 ${x(r1,a1)} ${y(r1,a1)}
          L ${x(r2,a1)} ${y(r2,a1)} A ${r2} ${r2} 0 ${grande} 0 ${x(r2,a0)} ${y(r2,a0)} Z`;
}

/* ══════════════════════ barras: rol ══════════════════════ */
function pintarBarras(items){
  const cont = $('#barras-rol');
  const datos = (items || []).filter(i => i.k !== 'Sin dato');
  const suma = datos.reduce((a,b) => a + b.n, 0) || 1;
  const max = Math.max(1, ...datos.map(d => d.n));
  const prev = new Map([...cont.querySelectorAll('.barra')]
    .map(e => [e.dataset.k, +e.querySelector('.barra-val').dataset.n || 0]));

  cont.innerHTML = datos.map(it => {
    const antes = prev.get(it.k) || 0;
    const nuevo = it.n > antes ? ' barra-nueva' : '';
    return `<div class="barra${nuevo}" data-k="${esc(it.k)}">
      <span class="barra-nom">${esc(it.etq || it.k)}</span>
      <span class="barra-pista"><i class="barra-fill" style="width:${(100*it.n/max).toFixed(1)}%"></i></span>
      <span class="barra-val" data-n="${it.n}">${it.n}<small>${Math.round(100*it.n/suma)}%</small></span>
    </div>`;
  }).join('');
}

/* ══════════════════════ unidades académicas ══════════════════════ */
function etiquetaUnidad(k, alternativa){
  const etq = (S.cfg && S.cfg.etiquetas_unidad) || {};
  return etq[k] || alternativa || k;
}

function pintarUnidades(items){
  const datos = (items || []).slice().sort((a,b) => b.n - a.n || a.k.localeCompare(b.k, 'es'));
  const max = Math.max(1, ...datos.map(d => d.n));
  const col = (S.cfg && S.cfg.colores_unidad) || {};
  $('#unidades').innerHTML = datos.map(it => {
    const c = col[it.k];
    // color institucional por facultad: pinta la barra y deja una pestaña al
    // costado (box-shadow inset para no mover la grilla). Sin color -> amarillo.
    const barra = c ? `;background:${c}` : '';
    const pesta = c ? ` box-shadow:inset 4px 0 0 ${c};` : '';
    return `
    <div class="uni" title="${esc(it.k)}: ${it.n}"${c ? ` data-color="${c}"` : ''} style="${pesta}">
      <span class="uni-nom">${esc(etiquetaUnidad(it.k, it.corta))}</span>
      <span class="uni-pista"><i class="uni-fill" style="width:${(100*it.n/max).toFixed(1)}%${barra}"></i></span>
      <span class="uni-val">${it.n}</span>
    </div>`;
  }).join('');
}

/* ══════════════════════ contadores por grupo ══════════════════════
   Cada grupo del config suma varias unidades (por ejemplo "Capital" = las 4
   facultades + el instituto IGTP). Se dibujan como un contador más del panel. */
function pintarGrupos(unidades){
  const cont = $('#kpi-grupos');
  if(!cont) return;
  const grupos = (S.cfg && S.cfg.grupos) || [];
  if(!grupos.length){ cont.innerHTML = ''; return; }
  const cuenta = new Map((unidades || []).map(u => [u.k, u.n]));
  cont.innerHTML = grupos.map(g => {
    const n = (g.unidades || []).reduce((a, k) => a + (cuenta.get(k) || 0), 0);
    const det = g.nota ? `<br>${esc(g.nota)}` : '';
    return `<div class="mini mini-grupo" title="${esc((g.unidades || []).join(' · '))}: ${n}">
      <span class="mini-num">${n}</span>
      <span class="mini-etq">${esc(g.etiqueta || g.nombre)}${det}</span>
    </div>`;
  }).join('');
}

/* ══════════════════════ ranking de sedes regionales ══════════════════════ */
function pintarSedes(items){
  const cont = $('#sedes');
  if(!cont) return;
  const datos = (items || []).filter(i => i.tipo === 'sede')
                            .sort((a,b) => b.n - a.n || a.corta.localeCompare(b.corta, 'es'));
  if(!datos.length){ cont.innerHTML = '<p class="vacio">Todavía no hay ingresos de sedes regionales</p>'; return; }
  const max = Math.max(1, ...datos.map(d => d.n));
  const prev = new Map([...cont.querySelectorAll('.sede')]
    .map(e => [e.dataset.k, +e.querySelector('.sede-val').dataset.n || 0]));
  cont.innerHTML = datos.map(it => {
    const nuevo = it.n > (prev.get(it.k) || 0) ? ' fila-nueva' : '';
    return `<div class="sede${nuevo}" data-k="${esc(it.k)}" title="${esc(it.k)}: ${it.n}">
      <span class="sede-nom">${esc(it.corta)}</span>
      <span class="sede-pista"><i class="sede-fill" style="width:${(100*it.n/max).toFixed(1)}%"></i></span>
      <span class="sede-val" data-n="${it.n}">${it.n}</span>
    </div>`;
  }).join('');
  $('#sedes-total').textContent = datos.length + ' de 12 sedes';
}

/* ══════════════════════ últimos ingresos ══════════════════════ */
function pintarUltimos(recientes){
  const lista = recientes || [];
  const maxI = lista.length ? lista[lista.length-1].i : -1;
  const nuevos = new Set();
  if(!S.primera){
    lista.forEach(r => { if(r.i > S.ultimoVisto) nuevos.add(r.i); });
  }
  S.ultimoVisto = Math.max(S.ultimoVisto, maxI);
  S.primera = false;

  const ult = lista.slice(-12).reverse();          // más reciente primero
  $('#ultimos').innerHTML = ult.map(r => {
    const lugar = r.tipo === 'sede' ? r.corta : etiquetaUnidad(r.unidad, r.corta);
    return `<li class="${nuevos.has(r.i) ? 'nuevo' : ''}">
      <span class="u-hora">${esc(r.hora)}</span>
      <span class="u-cuerpo">
        <span class="u-lugar">${esc(lugar)}</span>
        <span class="u-det">${esc(r.claustro)} · ${esc(r.rol)}</span>
      </span>
    </li>`;
  }).join('');
}

/* ══════════════════════ MAPA ══════════════════════ */
function pintarMapaBase(){
  const svg = $('#mapa');
  svg.setAttribute('viewBox', `0 0 ${M.W} ${M.H}`);
  const [x0,y0,x1,y1] = M.prov.bbox;
  const lat0 = (y0 + y1) / 2, kx = Math.cos(lat0 * Math.PI / 180);
  const px = lo => lo * kx, py = la => -la;
  const ax0 = px(x0), ax1 = px(x1), ay0 = py(y1), ay1 = py(y0);
  const s = Math.min((M.W - 2*M.margen) / (ax1-ax0), (M.H - 2*M.margen) / (ay1-ay0));
  const ox = (M.W - (ax1-ax0)*s)/2 - ax0*s;
  const oy = (M.H - (ay1-ay0)*s)/2 - ay0*s;
  M.proy = (lon, lat) => [px(lon)*s + ox, py(lat)*s + oy];

  const camino = anillo => anillo.map((p,i) => {
    const [x,y] = M.proy(p[0], p[1]);
    return (i ? 'L' : 'M') + x.toFixed(1) + ',' + y.toFixed(1);
  }).join('') + 'Z';

  svg.innerHTML = ['prov-fill','departamentos','prov-borde','nodos','anillos']
    .map(c => `<g id="capa-${c}"></g>`).join('');
  const pf = $('#capa-prov-fill'), dp = $('#capa-departamentos'), pb = $('#capa-prov-borde');

  M.prov.provincia.forEach(a => {
    pf.insertAdjacentHTML('beforeend', `<path class="provincia" d="${camino(a)}" stroke="none"/>`);
    pb.insertAdjacentHTML('beforeend', `<path d="${camino(a)}" fill="none"
      stroke="#111111" stroke-width="2.6" stroke-linejoin="round"/>`);
  });
  M.prov.departamentos.forEach(a =>
    dp.insertAdjacentHTML('beforeend', `<path class="dpto" d="${camino(a)}"/>`));

  svg.setAttribute('preserveAspectRatio', 'xMidYMid meet');
}

/* Radio del nodo: crece con la raíz del total (así 50 ingresos no aplastan a
   las sedes de 2). La pendiente y el tope están calibrados para que las sedes
   vecinas (Cruz del Eje / Capilla del Monte, Mina Clavero / Villa Dolores) no
   se solapen cuando el evento junta 400-500 ingresos. */
const radioNodo = n => Math.min(30, 7 + 1.5 * Math.sqrt(n));

function pintarMapa(unidades){
  if(!M.proy || !unidades) return;

  // agrupar por coordenada: Capital reúne rectorado + secretarías + facultades + instituto
  const grupos = new Map();
  unidades.forEach(u => {
    if(u.lat === null || u.lat === undefined) return;
    const k = u.lat.toFixed(3) + ',' + u.lon.toFixed(3);
    if(!grupos.has(k)) grupos.set(k, {lat:u.lat, lon:u.lon, n:0, tipo:u.tipo, corta:u.corta});
    const g = grupos.get(k);
    g.n += u.n;
    if(u.tipo === 'sede'){ g.tipo = 'sede'; g.corta = u.corta; }
  });

  const capaN = $('#capa-nodos');
  const vivos = new Set();
  const audit = [];                 // posiciones finales, para auditar desde tools/

  // de mayor a menor: los nodos chicos se dibujan encima y no quedan tapados
  [...grupos.entries()].sort((a,b) => b[1].n - a[1].n).forEach(([k, g]) => {
    vivos.add(k);
    const [x,y] = M.proy(g.lon, g.lat);
    const n = g.n;
    const R = radioNodo(n);
    const antes = S.prev.get(k) || 0;
    const salto = n - antes;

    let el = M.nodos.get(k);
    if(!el){
      const gr = document.createElementNS(NS, 'g');
      gr.setAttribute('class', 'nodo-g');
      gr.innerHTML = `<circle class="nodo-halo"/><circle class="nodo-separador"/><circle class="nodo-cuerpo"/>
                      <g class="nodo-puntos"></g>`;
      capaN.appendChild(gr);
      el = { g:gr, halo:gr.querySelector('.nodo-halo'), sep:gr.querySelector('.nodo-separador'),
             cuerpo:gr.querySelector('.nodo-cuerpo'), puntos:gr.querySelector('.nodo-puntos'),
             n:0, R:0, x:0, y:0 };
      M.nodos.set(k, el);
    }
    el.g.setAttribute('transform', `translate(${x.toFixed(1)},${y.toFixed(1)})`);
    el.x = x; el.y = y; el.R = R; el.n = n;

    el.cuerpo.setAttribute('r', R);
    el.cuerpo.setAttribute('class', 'nodo-cuerpo' + (g.tipo === 'sede' ? '' : ' capital'));
    el.halo.setAttribute('r', R + 7);
    el.sep.setAttribute('r', R + 3);

    // una marca por participante, en espiral de girasol dentro del círculo
    if(el.n !== n){
      const sep = (R - 2.6) / Math.sqrt(n);
      const dotR = Math.min(2.6, Math.max(0.85, sep * 0.46));
      let p = '';
      for(let i = 0; i < Math.min(n, 300); i++){
        const rr = sep * Math.sqrt(i + 0.5);
        const th = i * 2.39996323;
        p += `<circle class="nodo-punto" cx="${(rr*Math.cos(th)).toFixed(2)}"
               cy="${(rr*Math.sin(th)).toFixed(2)}" r="${dotR.toFixed(2)}"/>`;
      }
      el.puntos.innerHTML = p;
    }

    // Sin rótulos sobre el mapa: el nombre y el total de cada sede ya están en el
    // panel lateral, y un rótulo apartado del círculo (para no taparlo) se lee
    // como si perteneciera a otro nodo. En el mapa queda solo el círculo, con el
    // tamaño según la cantidad de ingresos.
    audit.push({ n, x, y, R });

    // ondas sonar por ingresos nuevos. Tope por nodo y tope global: cuando se
    // pega un lote grande de respuestas de golpe (una carga de prueba, por
    // ejemplo) el mapa se llenaba de aros y no se veía la provincia.
    if(salto > 0 && antes > 0){
      const ondas = Math.min(2, Math.max(1, Math.ceil(salto / 8)));
      for(let i = 0; i < ondas; i++){
        M.anillos.push({ x, y, t0: performance.now() + i*320, de: R,
                         hasta: R + 55 + Math.min(40, salto*4), dur: 1400 + i*140 });
      }
      if(M.anillos.length > 20) M.anillos.splice(0, M.anillos.length - 20);
    }
    if(salto > 0 || salto < 0 || !S.prev.has(k)) S.prev.set(k, n);
  });

  // se publican las posiciones y tamaños para auditarlos desde tools/verificar_mapa.py
  const svg = $('#mapa');
  if(svg) svg.setAttribute('data-nodos', JSON.stringify(
    { W: M.W, H: M.H, nodos: audit.map(a => ({ n: a.n, x: +a.x.toFixed(1),
                                               y: +a.y.toFixed(1), R: +a.R.toFixed(1) })) }));

  // nodos que desaparecieron (no debería pasar, pero por las dudas)
  M.nodos.forEach((el, k) => {
    if(!vivos.has(k)){ el.g.remove(); M.nodos.delete(k); S.prev.delete(k); }
  });
}

/* ══════════════════════ animación: sonar + respiración ══════════════════════ */
function animar(){
  const t = performance.now();
  const capaA = $('#capa-anillos');
  if(capaA){
    M.anillos = M.anillos.filter(a => t - a.t0 < a.dur + 200);
    let html = '';
    M.anillos.forEach(a => {
      if(t < a.t0) return;
      const p = Math.min(1, (t - a.t0) / a.dur);
      const e = 1 - Math.pow(1 - p, 3);             // easeOutCubic
      const r = a.de + (a.hasta - a.de) * e;
      html += `<circle class="sonar" cx="${a.x.toFixed(1)}" cy="${a.y.toFixed(1)}"
                 r="${r.toFixed(1)}" opacity="${((1 - p) * 0.75).toFixed(3)}"
                 stroke-width="${(3.2 - 2.4*p).toFixed(2)}"/>`;
    });
    capaA.innerHTML = html;
  }
  // respiración de los halos
  let k = 0;
  M.nodos.forEach(el => {
    const f = Math.sin(t/900 + k*1.7);
    el.halo.setAttribute('r', Math.max(2, el.R + 7 + 2.2*f + (el.n > 30 ? 2 : 0)));
    el.halo.setAttribute('opacity', (0.4 + 0.2*f).toFixed(3));
    k++;
  });
  requestAnimationFrame(animar);
}

/* ══════════════════════ utilidades ══════════════════════ */
function esc(s){
  return String(s === null || s === undefined ? '' : s)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}

/* ══════════════════════ carga de geodatos ══════════════════════ */
fetch('data/mapa.json', {cache:'no-store'})
  .then(r => r.json())
  .then(g => { M.prov = g; pintarMapaBase(); })
  .catch(() => {
    $('#pie-estado').textContent = 'No se pudieron cargar los geodatos (data/mapa.json)';
    $('#pie-estado').classList.add('alerta');
  });
