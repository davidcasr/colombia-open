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

- **Fuentes implementadas**: 1 — `divipola` (geografía: departamentos +
  municipios, DANE).
- **Próxima candidata sugerida**: ver tabla — la de menor dificultad entre las
  no implementadas (hoy: demografía o educación, 🟡 Fácil).

## Tabla de fuentes

| Dominio | Fuente oficial | Acceso | Dificultad | Estado |
|---|---|---|---|---|
| Geografía (códigos DIVIPOLA + centroides) | DANE, vía API Socrata de datos.gov.co (dataset `gdxc-w37w`) | API JSON directa, confirmada y estable | 🟢 Implementada | ✅ `divipola` — ver `src/extractors/divipola_extractor.py` |
| Geografía (geometría de polígonos, MGN) | DANE Geoportal (Marco Geoestadístico Nacional) | Shapefile por vigencia; **mecanismo de descarga directa sin JS no confirmado todavía** — requiere investigación adicional antes de implementar | 🟡 Media (pendiente de verificar) | ⬜ No implementada — ver nota abajo |
| Demografía (censo) | DANE CNPV 2018, `microdatos.dane.gov.co` | Descarga directa; hay mapeo de referencia en el paquete R `ColOpenData` | 🟡 Fácil | ⬜ No implementada |
| Educación | ICFES (pruebas Saber) / MinEducación SIMAT | Microdatos abiertos del ICFES, descarga directa | 🟡 Fácil | ⬜ No implementada |
| Calidad del aire | IDEAM — SISAIRE | Portal con descargas | 🟡 Media | ⬜ No implementada |
| Vivienda / edificación | DANE / Camacol | Boletines + censo (Excel) | 🟡 Media | ⬜ No implementada |
| Pobreza | DANE (monetaria / multidimensional) | Excel anual | 🟡 Media | ⬜ No implementada |
| Consumo eléctrico | XM (operador del mercado eléctrico) / UPME | XM tiene API pública (SINERGOX) — acceso sin verificar en detalle | 🟡 Media | ⬜ No implementada |
| Macroeconomía | Banco de la República | Tiene API de series — acceso sin verificar en detalle | 🟡 Media | ⬜ No implementada |
| Economía municipal / finanzas territoriales | DNP Terridata (basado en el FUT) | Sin API confirmada; solo descarga web por año (2000-2024) | 🟠 Difícil (requiere scraping) | ⬜ No implementada |
| Salud | MinSalud — SISPRO | Portal "bodega de datos", sin API pública clara | 🟠 Difícil | ⬜ No implementada |
| Clima | IDEAM | Catálogo fragmentado — podría terminar siendo un proyecto de investigación propio | 🟠 Difícil | ⬜ No implementada |
| Electoral | Registraduría — Observatorio Electoral | Sin API; datos no legibles por máquina según IDEA. Alternativa: `datoselectorales.org` (MOE, sociedad civil) | 🔴 Bloqueada sin scraping serio | ⬜ No implementada |
| Delincuencia | Policía Nacional — SIEDCO | No se confirmó portal de datos abiertos estructurado | 🔴 Sin fuente confirmada | ⬜ No implementada |

> Esta tabla se investigó por búsqueda web además de verificación directa de
> endpoints (curl/fetch) para la fila de geografía — las demás filas **no
> están verificadas contra código real** y pueden estar desactualizadas.
> Antes de implementar cualquiera, confirma el endpoint/URL actual con
> `/next-source` (que te obliga a este paso) o manualmente.

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
