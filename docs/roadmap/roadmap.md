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

- **Fuentes implementadas**: 2 — `divipola` (geografía: departamentos +
  municipios, DANE) y `demografia` (proyecciones de población municipal
  2018-2042, DANE).
- **Próxima candidata sugerida**: educación o delincuencia (ambas tienen
  endpoints Socrata confirmados en vivo, ver tabla). Para educación, el
  endpoint de Saber 11 (`kgxf-xxbe`) tiene ~7.1 millones de filas de
  microdato — requiere decidir una estrategia de agregación antes de
  implementar, no se puede publicar tal cual. Para delincuencia, solo el
  endpoint de hurto a personas (`4rxi-8m8d`) tiene códigos DANE limpios
  (`cod_depto`/`cod_muni`); los otros 2 endpoints de ese dominio
  (lesiones, hurto a residencias/comercios) solo traen `codigo_dane` de
  8-9 dígitos y nombres de municipio inconsistentes — más trabajo de
  normalización de lo que sugiere la tabla.

## Tabla de fuentes

| Dominio | Fuente oficial | Acceso | Dificultad | Estado |
|---|---|---|---|---|
| Geografía (códigos DIVIPOLA + centroides) | DANE, vía API Socrata de datos.gov.co (dataset `gdxc-w37w`) | API JSON directa, confirmada y estable | 🟢 Implementada | ✅ `divipola` — ver `src/extractors/divipola_extractor.py` |
| Geografía (geometría de polígonos, MGN) | DANE Geoportal, o mirror en HDX (Humanitarian Data Exchange) | Geoportal DANE: shapefile por vigencia, mecanismo sin JS no confirmado. **Mirror HDX confirmado en vivo 2026-10-17** (`data.humdata.org`, dataset `50ea7fee-...`, capa ADM2 = municipio, licencia CC BY-IGO, responde 302 a S3 firmado — ver nota abajo) | 🟢 Fácil vía HDX / 🟡 Media vía Geoportal directo | ⬜ No implementada — ver nota abajo |
| Demografía (censo/proyecciones) | DANE, proyecciones de población municipal 2018-2042 | **URL exacta confirmada en vivo 2026-10-18**: `dane.gov.co/files/censo2018/proyecciones-de-poblacion/Municipal/PPED-AreaMun-2018-2042_VP.xlsx` (xlsx directo, HTTP 200, hoja `PobMunicipalxÁrea`) | 🟡 Fácil | ✅ `demografia` — ver `src/extractors/demografia_extractor.py` |
| Educación | ICFES (Saber 11) / MinEducación (directorio de establecimientos) | **2 endpoints Socrata confirmados en vivo 2026-10-17**: Saber 11 → `datos.gov.co/resource/kgxf-xxbe.json` (CC BY-SA 4.0); directorio MEN → `datos.gov.co/resource/cfw5-qzt5.json` (CC BY-SA 4.0) | 🟡 Fácil | ⬜ No implementada |
| Calidad del aire | IDEAM — SISAIRE | Portal con descargas | 🟡 Media | ⬜ No implementada |
| Vivienda / edificación | DANE / Camacol | Boletines + censo (Excel) | 🟡 Media | ⬜ No implementada |
| Pobreza | DANE (monetaria / multidimensional) | Excel anual | 🟡 Media | ⬜ No implementada |
| Consumo eléctrico | XM (operador del mercado eléctrico) / UPME | XM tiene API pública (SINERGOX) — acceso sin verificar en detalle | 🟡 Media | ⬜ No implementada |
| Macroeconomía | Banco de la República | Tiene API de series — acceso sin verificar en detalle | 🟡 Media | ⬜ No implementada |
| Infraestructura urbana / puntos de interés | OpenStreetMap, vía extracto Geofabrik | **Confirmado en vivo 2026-10-17**: `download.geofabrik.de/south-america/colombia-latest.osm.pbf` (ODbL 1.0, © OpenStreetMap contributors). Requiere recorte con osmium/GDAL y filtrado por etiqueta (ej. `shop=supermarket`, `amenity=pharmacy`) — más trabajo de geoprocesamiento que un fetch de API | 🟡 Media | ⬜ No implementada — dominio nuevo, no mapeado antes de 2026-10-17 |
| Economía municipal / finanzas territoriales | DNP Terridata (basado en el FUT) | Sin API confirmada; solo descarga web por año (2000-2024) | 🟠 Difícil (requiere scraping) | ⬜ No implementada |
| Salud | MinSalud — SISPRO (nacional); REPS departamental sí existe en Socrata | Nacional: portal "bodega de datos", sin API pública clara. **Pista parcial 2026-10-17**: Gobernación de Antioquia publica su propio REPS (prestadores de salud) en Socrata — confirma que el dato existe en ese formato, pero es departamental, no nacional. Buscar si MinSalud publica un REPS nacional equivalente antes de implementar | 🟠 Difícil (nacional) | ⬜ No implementada |
| Clima | IDEAM | Catálogo fragmentado — podría terminar siendo un proyecto de investigación propio | 🟠 Difícil | ⬜ No implementada |
| Electoral | Registraduría — Observatorio Electoral | Sin API; datos no legibles por máquina según IDEA. Alternativa: `datoselectorales.org` (MOE, sociedad civil) | 🔴 Bloqueada sin scraping serio | ⬜ No implementada |
| Delincuencia | Policía Nacional / DIJIN, vía Observatorio del Ministerio de Defensa | **3 endpoints Socrata confirmados en vivo 2026-10-17** (CC BY-SA 4.0): hurto a personas → `datos.gov.co/resource/4rxi-8m8d.json`; lesiones personales → `datos.gov.co/resource/72sg-cybi.json`; hurto a residencias/comercios → `datos.gov.co/resource/6sqw-8cg5.json` | 🟡 Fácil (bajó de 🔴) | ⬜ No implementada |

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
