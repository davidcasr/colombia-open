# rethus

Registro Único Nacional del Talento Humano en Salud (RETHUS): conteo de
registros de talento humano en salud (médicos, enfermeros, auxiliares,
especialistas…) por perfil profesional, tipo de programa académico,
origen del título (local/extranjero) y tipo de institución, agregado por
año del acto administrativo de registro y por departamento/municipio de
**residencia** del profesional.

- **Fuente**: Ministerio de Salud y Protección Social (MinSalud) —
  "Registro Único Nacional del Talento Humano en Salud - Rethus"
  (`my8c-6xkk`), vía la API Socrata de datos.gov.co:
  <https://www.datos.gov.co/resource/my8c-6xkk.json>.
- **Licencia**: CC BY-SA 4.0 (explícita en el portal, atribución a
  MinSalud) — ver `docs/licenses/data_licenses.md`.
- **Extractor**: `src/extractors/rethus_extractor.py`.
- **Filas esperadas**: ~90297 (92373 filas crudas en la fuente, menos 2076
  excluidas por "SIN INFORMACION" — ver Limitaciones), confirmado en vivo
  el 2026-11-24. Suman 1 681 198 registros de talento humano.

El dato **ya viene agregado por la fuente** — no es microdato por
persona. `numero_registros` es un conteo, nunca una fila por profesional.

## Snapshot congelado — no es una serie viva

**Esta es la limitación más importante del dataset.** La fuente declara
"Frecuencia de Actualización: Anual" en su metadata de datos.gov.co, pero
`rowsUpdatedAt` y `publicationDate` del recurso Socrata marcan
**2022-05-30** (confirmado en vivo el 2026-11-24): las filas no se han
refrescado desde esa fecha. El año 2022
en los datos solo tiene 3429 filas (un año parcial, cortado en la fecha de
congelamiento) y no hay ninguna fila de 2023 en adelante salvo el outlier
de abajo. El `updatedAt` que muestra el buscador/catálogo de datos.gov.co
(2026-05-18 al momento de esta verificación) es un re-touch de metadata
del lado de Socrata, no un refresco real de las filas — no te fíes de esa
fecha para juzgar la frescura de este dataset.

En la práctica: trata este dataset como una **foto del talento humano en
salud registrado hasta mayo de 2022**, no como el estado actual del
registro. Mismo criterio que el snapshot censal de pobreza municipal
documentado en `docs/roadmap/roadmap.md`.

## Esquema

| Columna | Tipo | Descripción |
|---|---|---|
| `cod_dpto` | string (2 dígitos) | Código DIVIPOLA de departamento de residencia, parseado del prefijo de `departamentoresidencia` en la fuente (ej. "05 - ANTIOQUIA" → "05"). **Nunca convertir a int.** |
| `nombre_dpto` | string | Nombre del departamento, parseado del mismo campo. |
| `cod_mpio` | string (5 dígitos) | Código DIVIPOLA de municipio de residencia, parseado del prefijo de `municipioresidencia` (ej. "05120 - CÁCERES" → "05120") — join key hacia `municipios`. **Nunca convertir a int.** |
| `nombre_mpio` | string | Nombre del municipio, parseado del mismo campo. |
| `origen_titulo` | string | Origen del título profesional tal cual la fuente: "1 - LOCAL", "2 - EXTRANJERO" o "NO DEFINIDO". |
| `tipo_institucion` | string | Tipo de institución educativa tal cual la fuente: "1 - EDUCACIÓN SUPERIOR" o "2 - EDUCACIÓN PARA EL TRABAJO Y EL DESARROLLO HUMANO". |
| `tipo_programa` | string | Nivel del programa académico: AUXILIAR, TÉCNICO PROFESIONAL, TECNOLOGÍA, UNIVERSITARIA, ESPECIALIZACIÓN, MAESTRÍA, DOCTORADO o NO DEFINIDO. |
| `perfil_profesional` | string | Perfil profesional de salud tal cual la fuente, con su código embebido (ej. "P07 - MEDICINA", "A02 - AUXILIAR EN ENFERMERÍA"). 156 valores observados — incluye "SIN INFORMACION" como perfil cuando la fuente no lo clasificó (no se excluye: a diferencia de `departamentoresidencia`/`municipioresidencia`, esto no impide geocodificar la fila). |
| `anio_registro` | int | Año del acto administrativo de registro (`a_oactoadministrativo` en la fuente). Rango real observado: 1900-2022, más un outlier de 2028 — ver Limitaciones. |
| `numero_registros` | int | Conteo de registros de talento humano para esa combinación exacta de dimensiones. Siempre > 0. Súmalo para totales — nunca cuentes filas. |

Clave primaria: `(cod_mpio, origen_titulo, tipo_institucion, tipo_programa,
perfil_profesional, anio_registro)` — única por construcción de la fuente
(confirmada en las 92373 filas crudas) y validada en cada build.

## Uso

```python
import polars as pl
from colombia_open import ColombiaOpen

hub = ColombiaOpen()
rethus = hub.load_polars("rethus")

# Total de talento humano en salud registrado, por municipio
(
    rethus.group_by(["cod_mpio", "nombre_mpio"])
    .agg(pl.col("numero_registros").sum().alias("total"))
    .sort("total", descending=True)
)

# Médicos (perfil P07) registrados por año, nacional
(
    rethus.filter(pl.col("perfil_profesional") == "P07 - MEDICINA")
    .group_by("anio_registro")
    .agg(pl.col("numero_registros").sum().alias("total"))
    .sort("anio_registro")
)

# Talento humano en salud por 100 mil habitantes en Medellín: join con demografia
poblacion = hub.load_polars("demografia").filter(
    (pl.col("area_geografica") == "Total") & (pl.col("anio") == 2022)
)
(
    rethus.filter(pl.col("cod_mpio") == "05001")
    .select(pl.col("numero_registros").sum().alias("total_th_salud"))
    .join(poblacion.filter(pl.col("cod_mpio") == "05001").select("cod_mpio", "poblacion"), how="cross")
)
```

## Limitaciones conocidas

- **Snapshot congelado a 2022-05, no una serie viva** — ver la sección
  dedicada arriba. No uses este dataset para inferir tendencias recientes
  del talento humano en salud sin verificar primero si MinSalud publicó un
  recurso más actualizado.
- **Es residencia del profesional, no el lugar donde ejerce.** El
  municipio/departamento es el de residencia reportado al momento del
  registro — no equivale a dónde presta servicios de salud. No usar como
  proxy de oferta de talento humano por municipio sin esa salvedad.
- **No es microdato.** Cada fila ya es un conteo agregado por la fuente;
  no hay un identificador de persona ni es posible desagregar más allá de
  las dimensiones publicadas.
- **Filas sin municipio excluidas.** 2076 de 92373 filas crudas (2.2%)
  traen "SIN INFORMACION" en departamento y municipio de residencia a la
  vez (nunca uno solo) — se excluyen porque no hay código DIVIPOLA posible
  a partir de ese valor. Su conteo (26 465 registros solo en la mayor de
  esas filas) queda en las `notes` de la metadata de staging de cada
  build, nunca se descarta en silencio.
- **4 filas con año de registro "2028".** Defecto de captura conocido de
  la fuente (un año futuro no puede ser el año real de un acto
  administrativo hasta mayo de 2022). No se corrigen ni se excluyen — el
  validador las reporta como warning (`anio_registro posterior a 2022`).
- **`perfil_profesional` puede ser "SIN INFORMACION"** en registros que la
  fuente no alcanzó a clasificar por perfil — a diferencia del municipio,
  esto no impide publicar la fila (sí se sabe dónde reside el profesional).
- **Valores de texto con el código de la fuente embebido.** `origen_titulo`,
  `tipo_institucion` y `perfil_profesional` se publican tal cual la fuente
  los entrega (ej. "1 - LOCAL", "P07 - MEDICINA"), sin separar el código
  del nombre en columnas distintas — igual criterio que `arma_medio`/
  `modalidad_presunta` en los datasets de delincuencia.
- **Discrepancia de `cod_mpio` con `municipios` (DIVIPOLA)** — el
  validador reporta cualquier `cod_mpio` que no exista en el `municipios`
  vigente como warning, no como error (mismo criterio que los demás
  datasets de entidades distintas al DANE).
