# Roadmap — colombia-open

> **Qué es este archivo**: el mapa de fuentes de datos públicos de Colombia que
> `colombia-open` planea distribuir, con su nivel de dificultad de acceso y su
> estado de implementación. **No es una cola de trabajo con sprints** — es la
> lista priorizada desde la que `/next-source` elige la siguiente fuente a
> implementar.
>
> Filosofía: **una fuente por fin de semana**, de punta a punta (extractor +
> builder + validación + registro + tests + docs), nunca varias a medias. Ver
> `CLAUDE.md` para el detalle de por qué y `.claude/commands/next-source.md`
> para el flujo de arranque semanal.

## Estado actual

- **Fuentes implementadas**: 11 — `divipola` (geografía: departamentos +
  municipios, DANE), `municipios_geometria` (geometría de polígonos
  municipales, MGN/DANE vía HDX — segunda iteración de `divipola`),
  `demografia` (proyecciones de población municipal 2018-2042, DANE),
  `educacion_establecimientos` (directorio de establecimientos educativos
  2015-2025, MEN), `educacion_saber11` (resultados Saber 11 agregados por
  establecimiento y periodo, 2010-2022, ICFES),
  `delincuencia_hurto_personas` (víctimas de hurto a personas por
  municipio y día, 2003 a la fecha, MinDefensa/Policía),
  `delincuencia_lesiones_personales` (víctimas de lesiones personales y en
  accidente de tránsito por municipio, día, conducta, arma, género y grupo
  etario, 2010 a la fecha, Policía), `delincuencia_hurto_modalidades`
  (víctimas de hurto a residencias y entidades comerciales por municipio,
  día, arma, género y grupo etario, 2010 a la fecha, Policía),
  `infraestructura_poi` (puntos de interés urbanos — salud, educación,
  seguridad, finanzas, religión, gobierno, transporte, comercio —
  geocodificados por municipio, OpenStreetMap vía Geofabrik),
  `macroeconomia_trm` (Tasa de Cambio Representativa del Mercado diaria,
  1991 a la fecha, Superintendencia Financiera) y `calidad_aire` (los 6
  contaminantes del Índice de Calidad del Aire por estación, 2011 a la
  fecha, IDEAM).
- **Próxima candidata sugerida**: ninguna queda con acceso ya confirmado
  sin diseño pendiente — vivienda (Camacol/DANE) sigue sin verificar,
  pobreza municipal solo existe en años censales (requiere decisión de
  alcance), consumo eléctrico sin API confirmable, y los otros
  indicadores del Banco de la República (DTF, IBR, UVR) son candidatos
  fáciles (mismo patrón que `macroeconomia_trm`) pero sin verificar en
  detalle todavía.

## Tabla de fuentes

| Dominio | Fuente oficial | Acceso | Dificultad | Estado |
|---|---|---|---|---|
| Geografía (códigos DIVIPOLA + centroides) | DANE, vía API Socrata de datos.gov.co (dataset `gdxc-w37w`) | API JSON directa, confirmada y estable | 🟢 Implementada | ✅ `divipola` — ver `src/extractors/divipola_extractor.py` |
| Geografía (geometría de polígonos, MGN) | DANE Geoportal, o mirror en HDX (Humanitarian Data Exchange) | **Confirmado en vivo 2026-10-20** vía HDX: dataset `cod-ab-col` (`50ea7fee-f9af-45a7-8a52-abb9c790a0b6`), recurso "COL Administrative Divisions Shapefiles.zip" (~117MB), capa ADM2 = municipio (1122 filas), licencia CC BY-IGO 3.0 | 🟢 Fácil vía HDX | ✅ `municipios_geometria` — ver `src/extractors/municipios_geometria_extractor.py` |
| Demografía (censo/proyecciones) | DANE, proyecciones de población municipal 2018-2042 | **URL exacta confirmada en vivo 2026-10-18**: `dane.gov.co/files/censo2018/proyecciones-de-poblacion/Municipal/PPED-AreaMun-2018-2042_VP.xlsx` (xlsx directo, HTTP 200, hoja `PobMunicipalxÁrea`) | 🟡 Fácil | ✅ `demografia` — ver `src/extractors/demografia_extractor.py` |
| Educación (directorio de establecimientos) | MinEducación (MEN) | **Confirmado en vivo 2026-10-18**: `datos.gov.co/resource/cfw5-qzt5.json` (CC BY-SA 4.0 explícito). 606206 filas, 2015-2025, paginado — ~360MB/~7min por build. Defecto conocido de la fuente: `codigo_dane` tiene baja cardinalidad en 2023 (ver `docs/datasets/educacion_establecimientos.md`) | 🟡 Fácil | ✅ `educacion_establecimientos` — ver `src/extractors/educacion_establecimientos_extractor.py` |
| Educación (Saber 11, ICFES) | ICFES | **Confirmado en vivo 2026-10-21**: `datos.gov.co/resource/kgxf-xxbe.json` (CC BY-SA 4.0). 7109704 filas de microdato (2010-2022) agregadas por `(codigo_dane_establecimiento, periodo)` — join directo hacia `educacion_establecimientos` — a 105110 filas publicadas. Paginado por keyset (`:id`), no `$offset` (~7x más rápido a esta escala, ver docstring del extractor) | 🟡 Fácil (acceso) | ✅ `educacion_saber11` — ver `src/extractors/educacion_saber11_extractor.py` |
| Calidad del aire | IDEAM, vía datos.gov.co (no SISAIRE directo) | **Confirmado en vivo 2026-10-22**: `datos.gov.co/resource/kekd-7v7h.json` ("Calidad del Aire en Colombia (Promedio Anual)", CC BY-SA 4.0, atribución IDEAM). 30665 filas totales, 2011-2025, 513 estaciones, 344 municipios. Se publican solo los 6 contaminantes del ICA (PM10/PM2.5/SO2/O3/NO2/CO, ~15600 filas de microdato) — las 14 variables meteorológicas y PST/NO quedan fuera, documentado como alcance. Defecto real de la fuente: ~6600 combinaciones estación+contaminante+ventana+año vienen publicadas DOS VECES — colapsadas a 8985 filas publicadas | 🟡 Media (curación de variables, no de acceso) | ✅ `calidad_aire` — ver `src/extractors/calidad_aire_extractor.py` |
| Vivienda / edificación | DANE / Camacol | Boletines + censo (Excel) | 🟡 Media | ⬜ No implementada |
| Pobreza | DANE (monetaria / multidimensional) | **Investigado 2026-10-22**: no hay tasa de pobreza municipal anual en datos.gov.co — la pobreza monetaria/multidimensional del DANE solo se calcula a nivel municipal en años censales (2005, 2018; ver `qgpk-sefn`), y el dato anual (GEIH) es departamental/13 ciudades, no municipal. Implementar esto requeriría publicar solo años censales o cambiar la granularidad — decisión de alcance antes de empezar | 🟡 Media / requiere diseño de alcance | ⬜ No implementada |
| Consumo eléctrico | XM (operador del mercado eléctrico) / UPME | **Investigado 2026-10-22**: no se encontró una API pública confirmable de SINERGOX/SiMEM — solo un portal de descarga interactivo. Búsqueda en el catálogo de datos.gov.co tampoco encontró demanda eléctrica por municipio | 🟡 Media / acceso no confirmado | ⬜ No implementada |
| Macroeconomía (TRM) | Superintendencia Financiera (metodología Banco de la República) | **Confirmado en vivo 2026-10-22**: `datos.gov.co/resource/32sa-8pi3.json` (CC BY-SA 4.0). 8372 filas, 1991 a la fecha, serie diaria sin dimensión territorial — la fuente más simple del catálogo | 🟢 Fácil | ✅ `macroeconomia_trm` — ver `src/extractors/macroeconomia_trm_extractor.py` |
| Macroeconomía (otros indicadores: DTF, IBR, UVR) | Banco de la República, vía datos.gov.co | **Encontrados en vivo 2026-10-22** junto con TRM en el mismo catálogo (`gtwv-4pxq`, `ev8i-uzwt`, `mtic-nvgq`) — no verificados en detalle, candidatos naturales para ampliar el dominio macroeconomía si hay demanda | 🟢 Probablemente fácil (mismo patrón que TRM) | ⬜ No implementada |
| Infraestructura urbana / puntos de interés | OpenStreetMap, vía extracto Geofabrik | **Confirmado en vivo 2026-10-20**: `download.geofabrik.de/south-america/colombia-latest.osm.pbf` (~332MB, ODbL 1.0, © OpenStreetMap contributors). Filtrado con pyosmium (`FileProcessor` + `KeyFilter` a nivel C++, ~5s en vez de ~25min) por lista curada de `amenity`/`shop`; geocodificado con join espacial contra `municipios_geometria`. 58046 filas publicadas (58494 nodos clasificados, ~450 excluidos por geocodificación) | 🟡 Media (geoprocesamiento) | ✅ `infraestructura_poi` — ver `src/extractors/infraestructura_poi_extractor.py` |
| Economía municipal / finanzas territoriales | DNP Terridata (basado en el FUT) | Sin API confirmada; solo descarga web por año (2000-2024) | 🟠 Difícil (requiere scraping) | ⬜ No implementada |
| Salud | MinSalud — SISPRO (nacional); REPS departamental sí existe en Socrata | Nacional: portal "bodega de datos", sin API pública clara. **Pista parcial 2026-10-17**: Gobernación de Antioquia publica su propio REPS (prestadores de salud) en Socrata — confirma que el dato existe en ese formato, pero es departamental, no nacional. Buscar si MinSalud publica un REPS nacional equivalente antes de implementar | 🟠 Difícil (nacional) | ⬜ No implementada |
| Clima | IDEAM | Catálogo fragmentado — podría terminar siendo un proyecto de investigación propio | 🟠 Difícil | ⬜ No implementada |
| Electoral | Registraduría — Observatorio Electoral | Sin API; datos no legibles por máquina según IDEA. Alternativa: `datoselectorales.org` (MOE, sociedad civil) | 🔴 Bloqueada sin scraping serio | ⬜ No implementada |
| Delincuencia (hurto a personas) | Policía Nacional, vía Ministerio de Defensa | **Confirmado en vivo 2026-10-19**: `datos.gov.co/resource/4rxi-8m8d.json` (CC BY-SA 4.0). 651200 filas ya agregadas por fecha + municipio, 2003 a la fecha, ~1.5 min por build. Defecto conocido de la fuente: 2008 casi sin desagregación municipal (365 filas "SIN ESTABLECER", excluidas — ver `docs/datasets/delincuencia_hurto_personas.md`) | 🟡 Fácil | ✅ `delincuencia_hurto_personas` — ver `src/extractors/delincuencia_hurto_personas_extractor.py` |
| Delincuencia (lesiones personales) | Policía Nacional (DIPON), vía datos.gov.co | **Confirmado en vivo 2026-10-19**: `datos.gov.co/resource/72sg-cybi.json` (CC BY-SA 4.0). 1381416 filas, 2010 a la fecha, con conducta, arma, género y grupo etario; `codigo_dane` de 8 dígitos (municipio + centro poblado) que se colapsa a municipio → ~1377323 filas, ~1 min por build. Mezcla lesiones dolosas y culposas en tránsito (columna derivada `tipo_lesion`) — ver `docs/datasets/delincuencia_lesiones_personales.md` | 🟡 Media (normalización de códigos) | ✅ `delincuencia_lesiones_personales` — ver `src/extractors/delincuencia_lesiones_personales_extractor.py` |
| Delincuencia (hurto por modalidades) | Policía Nacional (DIPON), vía datos.gov.co | **Confirmado en vivo 2026-10-20** (CC BY-SA 4.0): `datos.gov.co/resource/6sqw-8cg5.json` (653384 filas crudas; residencias y entidades comerciales). Mismo formato que lesiones: microdato por hecho, `codigo_dane` de 8 dígitos y nombres con sufijo "(CT)" | 🟡 Media (normalización de códigos; reusó la de lesiones) | ✅ `delincuencia_hurto_modalidades` — ver `src/extractors/delincuencia_hurto_modalidades_extractor.py` |

> Esta tabla se investigó por búsqueda web además de verificación directa de
> endpoints (curl/fetch). Las filas de geografía (ambas), demografía,
> educación, delincuencia e infraestructura/POIs se verificaron **en vivo**
> (HTTP 200 o redirect válido) el 2026-10-17, cruzando hallazgos con el
> proyecto hermano `vivireneloriente` (ver su `config/fuentes.yaml` y
> `docs/decisions/` para el detalle de cómo verificó cada una originalmente).
> Las demás filas **no están verificadas contra código real** y pueden estar
> desactualizadas. Verificar en vivo no es lo mismo que implementar: antes de
> escribir el extractor, sigue confirmando el esquema completo y los límites
> de paginación con `/next-source` o manualmente.

## Por qué geografía fue primero

`divipola` (departamento + municipio, con nombre y centroide) es la tabla base
de códigos territoriales sobre la que se hace join con casi todas las demás
capas futuras (demografía, educación, pobreza, salud...). Es también la
fuente con el acceso más estable y confirmado de todo este mapeo: API JSON
pública y documentada, sin scraping.

**Decisión de alcance (2026-10-17)**: la primera iteración de `divipola` NO
incluye la geometría de polígonos del MGN (solo centroides lat/lon). El
mecanismo de descarga directa y estable del MGN por vigencia en el Geoportal
del DANE no se pudo confirmar sin JavaScript durante esta sesión (ver
intentos en el historial de la sesión que creó este archivo). Agregar la
geometría de polígonos es candidata a **segunda iteración de la misma fuente**
(no una fuente nueva), una vez se confirme un mecanismo de descarga
reproducible (shapefile versionado, servicio ArcGIS/WFS, o espejo estable).
Si investigas esto, documenta el hallazgo aquí antes de implementar.

**Actualización (2026-10-17)**: se encontró y verificó en vivo un espejo
estable — HDX (Humanitarian Data Exchange) redistribuye el shapefile ADM2
del DANE con descarga directa (sin JS) y licencia CC BY-IGO. Ver la fila de
geometría en la tabla arriba. Sigue siendo segunda iteración de `divipola`,
no fuente nueva — pero el bloqueo original (sin mecanismo de descarga
confirmado) ya no aplica.

**Actualización (2026-10-20)**: implementada como `municipios_geometria`,
dataset separado de `municipios` (mismo `cod_mpio` como join key) para no
cargarle a quien solo necesita nombre/centroide con el peso de los
polígonos — ver `docs/datasets/municipios_geometria.md`.

## Cómo agregar la siguiente fuente

1. Corre `/next-source` — lee esta tabla, propone la fuente candidata (menor
   dificultad entre las no implementadas) y arranca la skill `new-source`
   sobre ella.
2. O manualmente: elige una fila 🟢/🟡, verifica su endpoint/URL actual, y usa
   la skill `new-source` (`.claude/skills/new-source/SKILL.md`) con el nombre
   de la fuente y su URL.
3. Al terminar: marca la fila como implementada en esta tabla, con el link al
   extractor correspondiente (mismo formato que la fila de geografía).

## Fuentes rechazadas o en pausa

Ninguna todavía — el proyecto es demasiado joven para tener rechazos. Cuando
se descarte una fuente candidata (ej. por licencia restrictiva o acceso
irrecuperable), documenta el motivo en una tabla aquí en vez de borrar la
fila de arriba — y no la re-audites después sin evidencia nueva.
