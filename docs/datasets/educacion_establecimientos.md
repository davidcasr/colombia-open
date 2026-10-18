# educacion_establecimientos

Directorio único de establecimientos educativos de Colombia (preescolar,
básica y media), años 2015-2025.

- **Fuente**: Ministerio de Educación Nacional (MEN) — "Directorio único
  de establecimientos educativos", vía la API Socrata de datos.gov.co:
  <https://www.datos.gov.co/resource/cfw5-qzt5.json>
- **Licencia**: CC BY-SA 4.0 (explícita en el portal) — ver
  `docs/licenses/data_licenses.md`.
- **Extractor**: `src/extractors/educacion_establecimientos_extractor.py`.
- **Filas esperadas**: ~606206 (confirmado en vivo el 2026-10-18), 2015-2025.

## Nota de volumen

A diferencia de las demás fuentes del catálogo, este dataset es pesado:
~360MB de JSON crudo, descargado paginado en bloques de 50000 filas, ~7
minutos por build. Se publica el historial completo 2015-2025 (no solo el
año vigente) como decisión de alcance explícita — ver el commit que agregó
esta fuente para el detalle de la discusión.

## Esquema

| Columna | Tipo | Descripción |
|---|---|---|
| `anio` | int | Año del reporte, 2015 a 2025. |
| `cod_dpto` | string (2 dígitos) | Código DIVIPOLA de departamento. **Nunca convertir a int.** |
| `nombre_dpto` | string | Nombre del departamento. |
| `cod_secretaria` | string | Código de la secretaría de educación certificada (MEN, sin ancho fijo documentado — no es un código DIVIPOLA). |
| `nombre_secretaria` | string | Nombre de la secretaría de educación certificada. |
| `cod_mpio` | string (5 dígitos), nullable | Código DIVIPOLA de municipio — join key hacia `municipios`. **Nunca convertir a int.** Nulo en 25 filas conocidas (ver limitación abajo) — nunca se fabrica un valor de reemplazo. |
| `nombre_mpio` | string | Nombre del municipio. |
| `codigo_dane_establecimiento` | string (12 dígitos) | Identificador del establecimiento según el MEN. **Ver limitación conocida abajo: no es confiable como clave única para el año 2023.** |
| `nombre_establecimiento` | string | Nombre del establecimiento educativo. |
| `cod_sector` | string | Código de sector (`"1001"` oficial, `"1002"` no oficial). |
| `sector` | string | `"OFICIAL"` / `"NO_OFICIAL"`. |
| `cod_caracter` | int, nullable | Código de carácter académico. La fuente lo entrega inconsistente (a veces `"-"`, a veces una cadena tipo `"817.000000"`) — normalizado a entero o `null`. |
| `caracter` | string | Descripción del carácter académico (ej. "Académico", "Técnico/Academico"), o `"-"`. |
| `cod_calendario` | string | Código de calendario académico. |
| `calendario` | string | `"A"` / `"B"`. |
| `direccion` | string, nullable | Dirección del establecimiento. |
| `barrio_vereda` | string, nullable | Barrio o vereda. |
| `telefono` | string, nullable | Teléfono de contacto. |
| `email` | string, nullable | Correo de contacto. |
| `rector` | string, nullable | Nombre del rector. |
| `total_matricula` | int, nullable | Matrícula total reportada para ese año. |
| `cantidad_sedes` | int, nullable | Número de sedes del establecimiento. |

No hay una clave primaria de fila garantizada por la fuente — ver la
limitación conocida abajo.

## Uso

```python
from colombia_open import ColombiaOpen

hub = ColombiaOpen()
educacion = hub.load_polars("educacion_establecimientos")

# Establecimientos oficiales de Medellín en 2024
educacion.filter(
    (educacion["cod_mpio"] == "05001")
    & (educacion["anio"] == 2024)
    & (educacion["sector"] == "OFICIAL")
)

hub.cross_view(["educacion_establecimientos", "municipios"], on="cod_mpio")
```

## Limitaciones conocidas

- **`codigo_dane_establecimiento` no es una clave primaria garantizada por
  la fuente, ni siquiera en años "normales".** Confirmado en vivo el
  2026-10-18: incluso los años con menos ruido tienen un puñado de
  duplicados genuinos (ej. 2015: 11 duplicados sobre 19610 filas; 2024: 79
  sobre 18076), y **2023 tiene un defecto sistémico mucho más severo**
  (416716 filas para solo 3043 códigos distintos — miles de
  establecimientos distintos comparten el mismo código, ej.
  `"105001000000"` repetido en decenas de colegios de Medellín, cada uno
  con nombre, dirección y rector distintos). Nada de esto se trata como
  error de clave duplicada — el validador (`src/validation/_educacion.py`)
  reporta ambos casos como **warning**, diferenciando en el texto "ruido
  normal" de "posible defecto sistémico", detectado dinámicamente por año
  (no hardcodea "2023"). No se fabrica un identificador sintético para
  tapar ninguno de los dos casos. Si necesitas una clave de fila propia,
  no asumas que `codigo_dane_establecimiento` es único — considera
  `(cod_mpio, anio, nombre_establecimiento)` con la limitación de que
  nombres pueden repetirse legítimamente entre municipios distintos.
- **25 filas (todas de 2023) no traen `cod_mpio`.** Confirmado en vivo el
  2026-10-18: Socrata omite el campo `cod_dane_municipio` del JSON en vez
  de mandarlo como `null` para esas filas (mismo año con el defecto de
  `codigo_dane` de arriba). El extractor nunca lanza por esto — usa
  `.get()` en vez de indexación directa — y el validador lo reporta como
  warning, no error. Si necesitas geografía completa, filtra esas 25 filas
  (`cod_mpio` nulo) antes de hacer `cross_view` con `municipios`.
- **Discrepancia de `cod_mpio` con `municipios` (DIVIPOLA)** — igual que
  en `demografia`: este dataset y `municipios` son productos de entidades
  distintas (MEN vs. DANE) con ciclos de actualización propios. El
  validador reporta cualquier `cod_mpio` que no exista en el `municipios`
  vigente como warning, no como error.
- **`cod_secretaria` no tiene un ancho fijo documentado** — a diferencia de
  `cod_dpto`/`cod_mpio` (códigos DIVIPOLA con ancho fijo conocido), no hay
  evidencia de una convención de ancho para los códigos de secretaría de
  educación del MEN, así que se publican tal cual los entrega la fuente,
  sin `.zfill()`.
