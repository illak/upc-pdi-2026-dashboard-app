# Tablero en vivo · Primera Jornada de Construcción Participativa del PDI

Tablero de una sola pantalla, sin scroll, que muestra **en vivo los ingresos registrados**
en la jornada a partir del formulario de registro. Está pensado para quedar visible en un
televisor o proyector durante todo el evento: fondo blanco, amarillo institucional y negro,
y se actualiza solo cada pocos segundos.

No necesita servidor: es un sitio estático (HTML + CSS + JavaScript) que el navegador lee
directamente de la planilla de respuestas. Por eso funciona publicado en GitHub Pages y
también sin conexión, sin instalar nada.

---

## Qué muestra

| Panel | Contenido |
|---|---|
| **Cabecera** | Logo institucional, título del evento, total de ingresos y reloj en vivo |
| **Claustro** | Dona con la distribución por claustro (Docente, No docente, Estudiantil, Graduados) |
| **Rol o función** | Barras horizontales por rol, ordenadas de mayor a menor |
| **Procedencia** | **Mapa de la provincia** con un círculo por sede regional, ubicado en su localidad |
| **Sedes regionales** | Ranking de las 12 sedes con su total |
| **Últimos ingresos** | Los 12 registros más recientes, del más nuevo al más viejo |
| **Unidad académica** | Grilla con todas las dependencias que registraron ingresos |

En el mapa, **el tamaño del círculo representa la cantidad de ingresos** de esa sede y cada
marca negra adentro es una persona. Cuando entra gente nueva, del círculo salen ondas tipo
sonar. El mapa **no lleva nombres**: los totales exactos están en el ranking lateral y en la
grilla inferior, y así ningún rótulo queda ambiguo sobre a qué círculo pertenece.

En la grilla de unidades académicas, las **facultades se identifican con su color
institucional** (Arte y Diseño, Educación y Salud, Educación Física, Turismo y Ambiente, más
el instituto IGTP), y el resto de las dependencias usa el amarillo UPC.

---

## Cómo funciona

```
[ Formulario de registro ]  →  [ Planilla de respuestas ]  →  [ Tablero en la pantalla ]
                                        ▲
                              el navegador lee cada 3 s
```

El formulario escribe en la planilla cuando alguien responde. La planilla no "avisa" a
nadie, así que el tablero la consulta periódicamente. De dónde la lee se elige con
`fuente.modo` en `web/data/config.json`; el modo **`auto`** (recomendado) prueba en orden y
usa el primero que responda:

| modo | qué usa | cuándo conviene |
|---|---|---|
| `auto` | servidor local → API de Sheets → CSV → snapshot → demo | dejarlo y olvidarse |
| `api` | API de Google Sheets v4 desde el navegador | lectura al segundo (requiere clave de API) |
| `csv` | planilla pública exportada como CSV | sin configurar nada extra |
| `json` | snapshot ya procesado (`data/estado.json`) | pantalla sin internet |
| `demo` | datos simulados | presentaciones y pruebas |

**Demoras reales:** el tablero mira cada **3 segundos**, pero Google cachea la exportación
CSV alrededor de **1 minuto**. Si se necesita más inmediatez, el camino es el servidor local
o la API.

---

## Cómo verlo

- **Publicado:** https://illak.github.io/upc-pdi-2026-dashboard-app/
- **Con la planilla:** agregar `?planilla=<id>` la primera vez (queda recordado)
- **Con datos simulados, sin depender de la planilla:** agregar `?demo=1` a la dirección
- **En una computadora, sin publicar nada:**

```bash
python3 -m http.server 8781 --directory web     # luego http://localhost:8781/
```

Para dejarlo fijo en la pantalla del evento: pantalla completa con **F11**.

---

## Cómo se conecta a los datos

**El identificador de la planilla se pasa por la dirección**, no está escrito en el
repositorio (que es público):

```
https://<usuario>.github.io/<repositorio>/?planilla=<id-de-la-planilla>
```

Al abrirla una vez así, **el navegador lo recuerda**: después alcanza con la dirección a
secas. Para olvidarlo, `?planilla=` (vacío). La planilla tiene que estar compartida como
*cualquiera con el enlace: lector* para que el navegador pueda leerla sin credenciales.

Todo lo que no es el identificador —la pestaña, el orden de columnas, los colores por
facultad, los textos y los contadores— se configura en un solo archivo:
**`web/data/config.json`**.

Parámetros útiles en la dirección:

| parámetro | para qué |
|---|---|
| `?planilla=<id>` | indica la planilla (y el navegador la recuerda) |
| `?gid=<n>` / `?hoja=<nombre>` | elegir otra pestaña de la misma planilla |
| `?demo=1` | datos simulados, sin leer la planilla |
| `?fuente=csv` / `?fuente=json` / `?fuente=demo` | forzar una fuente |
| `?url=<csv>` | probar otra planilla o un CSV alternativo sin tocar nada más |

Si no hay ninguna planilla indicada, el tablero avisa en el pie de página
(`falta la planilla: agregá ?planilla=<id>`) y muestra el último snapshot guardado.

---

## Privacidad

La pestaña que lee el tablero **no incluye la columna de correos**: solo fecha, unidad
académica, claustro y rol. El tablero nunca muestra ni descarga direcciones de correo.

---

## Archivos principales

```
web/                       el sitio que se publica
  index.html               estructura de los paneles
  estilo.css               apariencia (paleta institucional)
  app.js                   dibujo de los gráficos y el mapa
  datos.js                 lectura de la planilla, normalización y conteo
  data/config.json         configuración: pestaña y columnas de la planilla, colores, textos
  data/sedes.json          cada sede y su coordenada
  data/mapa.json           contorno de la provincia y departamentos
  assets/logo-upc.png      isologotipo institucional

server.py                  servidor opcional para leer una planilla PRIVADA
gapi.py                    acceso a Google con credenciales propias (lo usa server.py)
tools/                     utilidades: datos de prueba y verificaciones
```

El tablero **no usa librerías externas**: ni CDN, ni tipografías descargadas. Todo el
dibujo es SVG generado por el propio código, así que funciona sin internet.

---

## Datos de prueba y verificaciones

```bash
# genera respuestas de prueba con la misma estructura que la planilla
python3 tools/csv_prueba.py 180 web/data/pruebas.csv
#   y se miran con:  http://localhost:8781/?fuente=csv&url=data/pruebas.csv

# comprueba que cada opción del formulario se clasifique bien
python3 tools/verificar_mapeo.py

# comprueba que ningún círculo del mapa se salga del área dibujada
python3 tools/verificar_mapa.py --dom /tmp/dom.html
```

Los datos de prueba **no** son datos de la jornada: son inventados y se borran antes de
publicar. Si se generan en `web/data/`, hay que eliminarlos para no dejarlos en el sitio.

---

## Publicar cambios

Cada push a `main` publica automáticamente el contenido de `web/` en GitHub Pages, y el
sitio queda en `https://<usuario>.github.io/<repositorio>/`.

La primera vez hay que habilitar Pages en el repositorio: **Settings → Pages → Source:
GitHub Actions**. Sin ese paso el workflow falla con `Get Pages site failed`, porque la
acción consulta la configuración del sitio y recibe 404 si todavía no existe. El estado de
cada publicación se ve en la pestaña **Actions** del repositorio.
