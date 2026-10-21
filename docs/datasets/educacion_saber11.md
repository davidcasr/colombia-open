# educacion_saber11

Resultados de la prueba Saber 11 (ICFES), agregados por establecimiento
educativo y periodo de aplicación — promedio por materia y número de
estudiantes presentados. 2010 a 2022.

- **Fuente**: ICFES — "Resultados únicos Saber 11" (`kgxf-xxbe`), vía la
  API Socrata de datos.gov.co: <https://www.datos.gov.co/resource/kgxf-xxbe.json>
- **Licencia**: CC BY-SA 4.0 (explícita en el portal, atribución al ICFES)
  — ver `docs/licenses/data_licenses.md`.
- **Extractor**: `src/extractors/educacion_saber11_extractor.py`.
- **Filas esperadas**: ~105110 (fuente: 7109704 filas de microdato
  confirmadas en vivo el 2026-10-21, agregadas por establecimiento+periodo
  — ver Granularidad; 3377 excluidas por falta de código, ver Limitaciones).

## Decisión de alcance: por qué por establecimiento, no por municipio

La primera versión de este diseño agregaba solo por municipio y periodo.
Se descartó: dejaba el resultado "suelto", sin forma de relacionarlo con
un colegio específico de `educacion_establecimientos`. La versión
publicada agrega por **establecimiento**, porque:

- `codigo_dane_establecimiento` (12 dígitos) es la **misma clave y el
  mismo nivel de granularidad** que `educacion_establecimientos.codigo_dane_establecimiento`
  — join directo entre los dos datasets.
- Es nivel **institución**, no "sede": confirmado en vivo, 12125
  instituciones distintas en los 12 años de la fuente (consistente con el
  total real de IE del país), frente a ~13691 valores distintos del campo
  separado `cole_cod_dane_sede` (más granular, no usado aquí).
- **Nunca se publica microdato por estudiante** — ni por volumen (7.1M
  filas) ni por sensibilidad de los datos personales que trae la fuente
  cruda (`fami_*`, fecha de nacimiento, documento). Variables
  socioeconómicas quedan fuera de esta primera iteración.

## Granularidad y el cambio de estructura de 2014

Antes del periodo `20142`, la prueba (anterior a la reforma de ICFES de
2014) solo reportaba `punt_matematicas` y `punt_ingles` — los campos
`punt_global`, `punt_lectura_critica`, `punt_sociales_ciudadanas` y
`punt_c_naturales` no existen en la fuente para esos periodos (quedan
`null`, no se fabrican). Se confirmó en vivo que la escala de
matemáticas/inglés **sí es comparable** antes y después de la reforma
(promedio ~50 en 2010 y ~51 en 2016 en la misma escala ~0-100) — por eso
se publica el rango completo 2010-2022 en vez de truncar al periodo
post-reforma.

Una fila = un establecimiento + un periodo de aplicación (`periodo`,
formato `AAAAP`, ej. `"20194"`). `anio` es el año derivado del periodo,
para joins con datasets anuales.

## Esquema

| Columna | Tipo | Descripción |
|---|---|---|
| `codigo_dane_establecimiento` | string (12 dígitos) | **Join key hacia `educacion_establecimientos.codigo_dane_establecimiento`** — mismo formato, mismo nivel (institución). |
| `periodo` | string | Periodo de aplicación tal como lo reporta ICFES (`"20194"` = año 2019, segunda mitad/calendario). |
| `anio` | int | Año derivado de `periodo` — para joins con `demografia`. |
| `cod_dpto` | string (2 dígitos) | Código DIVIPOLA de departamento, ubicación del colegio. **Nunca convertir a int.** |
| `cod_mpio` | string (5 dígitos) | Código DIVIPOLA de municipio, ubicación del colegio — join key hacia `municipios`. **Nunca convertir a int.** |
| `naturaleza` | string, nullable | `"OFICIAL"` / `"NO OFICIAL"`. |
| `n_estudiantes` | int | Número de presentaciones agregadas en ese establecimiento-periodo. |
| `prom_matematicas` | float | Promedio simple. Disponible en **todo** el rango 2010-2022. |
| `prom_ingles` | float | Promedio simple. Disponible en **todo** el rango 2010-2022. |
| `prom_lectura_critica` | float, nullable | Promedio simple. **Nulo antes de `20142`** (la prueba no lo reportaba). |
| `prom_sociales_ciudadanas` | float, nullable | Ídem. |
| `prom_c_naturales` | float, nullable | Ídem. |
| `prom_global` | float, nullable | Ídem — puntaje compuesto 0-500 introducido en la reforma de 2014. |

Clave primaria: `(codigo_dane_establecimiento, periodo)` — garantizada
única por la agregación del extractor y validada en cada build.

## Uso

```python
import polars as pl
from colombia_open import ColombiaOpen

hub = ColombiaOpen()
saber11 = hub.load_polars("educacion_saber11")
establecimientos = hub.load_polars("educacion_establecimientos")

# Relacionar resultados con el directorio de establecimientos (sector,
# jornada, matrícula...) del mismo año
saber11.filter(pl.col("anio") == 2022).join(
    establecimientos.filter(pl.col("anio") == 2022),
    on="codigo_dane_establecimiento",
    how="left",
)

# Brecha oficial vs. no oficial en matemáticas, por año
(
    saber11.group_by(["anio", "naturaleza"])
    .agg(pl.col("prom_matematicas").mean(), pl.col("n_estudiantes").sum())
    .sort("anio")
)

# Evolución de un municipio en el tiempo (requiere sumar/ponderar por
# establecimiento si quieres un promedio municipal — aquí, solo listar)
saber11.filter(pl.col("cod_mpio") == "05001").sort("periodo")
```

## Limitaciones conocidas

- **No es microdato.** Esta es una agregación propia de `colombia-open`
  sobre el microdato público de ICFES — para análisis a nivel de
  estudiante individual, usa la fuente original (`kgxf-xxbe` en
  datos.gov.co), no este dataset.
- **El join hacia `educacion_establecimientos` hereda el ruido ya
  documentado de ese dataset** en `codigo_dane_establecimiento` (algunos
  duplicados en años "normales"). El defecto severo de 2023 documentado
  allá **no aplica aquí** — Saber 11 solo llega hasta 2022, no se solapan.
- **~3377 de 7.1M filas de microdato (0.05%) se excluyen** antes de
  agregar, por no traer `cole_cod_dane_establecimiento` o
  `cole_cod_mcpio_ubicacion` en la fuente — no se fabrica un valor de
  reemplazo.
- **`prom_lectura_critica`/`prom_sociales_ciudadanas`/`prom_c_naturales`/
  `prom_global` son `null` antes del periodo `20142`** — no es un dato
  faltante de este extractor, la prueba no los reportaba en esa época.
- **`punt_ingles = "-1"` es un valor centinela de la fuente en periodos
  legacy (2010-2013), no un puntaje real.** Confirmado en vivo el
  2026-10-21: 1516 filas de microdato (de 7.1M), todas de periodos
  `20101`-`20132`, nunca en `punt_matematicas` ni en periodos modernos —
  significa "no se administró esta parte de la prueba ese periodo". Se
  convierte a `null` antes de promediar (si no, un solo estudiante con
  "-1" entre 20+ vuelve negativo el promedio del establecimiento). Ver
  `_parse_float()` en el extractor.
- **Sin variables socioeconómicas.** `fami_estratovivienda`,
  `fami_tieneinternet`, etc. existen en la fuente cruda pero no se
  publican en esta primera iteración — candidata a segunda iteración si
  hay demanda (documentado, no implementado especulativamente).
- **Discrepancia de `cod_mpio` con `municipios` (DIVIPOLA)** — igual que
  en `educacion_establecimientos`: ICFES y DANE son entidades distintas
  con ciclos de actualización propios. El validador reporta cualquier
  `cod_mpio` que no exista en `municipios` vigente como warning, no error.
- **Paginación por keyset, no `$offset`** (detalle de implementación, ver
  docstring del extractor) — si alguna vez necesitas replicar la consulta
  a mano contra la API de Socrata, `$offset` se vuelve muy lento a esta
  escala (confirmado en vivo: ~87s por página de 100k en offset~7M, contra
  ~12s con keyset).
