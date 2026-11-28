# agro_eva

Evaluaciones Agropecuarias Municipales (EVA): área sembrada, área
cosechada, producción y rendimiento agrícola por municipio, cultivo y
periodo, de **2006 a 2025**. Es la estadística oficial de producción
agrícola municipal de Colombia.

El dataset **une dos series oficiales** que se suceden en el tiempo, cada
una publicada por una entidad distinta y con su propio esquema de columnas:

| Serie (`serie_fuente`) | Entidad | Recurso datos.gov.co | Años | Filas |
|---|---|---|---|---|
| `minagricultura_2006_2018` | Ministerio de Agricultura y Desarrollo Rural | [`2pnw-mmge`](https://www.datos.gov.co/resource/2pnw-mmge.json) | 2006-2018 | 206 068 |
| `upra_2019_2025` | Unidad de Planificación Rural Agropecuaria (UPRA) | [`uejq-wxrr`](https://www.datos.gov.co/resource/uejq-wxrr.json) | 2019-2025 | 166 732 |

Las dos series no se solapan en años (confirmado en vivo y validado en cada
build). La serie de MinAgricultura está cerrada (sin actualizar desde
2019-11); UPRA ejecuta las EVA desde 2019 y su serie sigue viva.

- **Licencia**: CC BY-SA 4.0 en ambas series (explícita en el portal) —
  atribución a UPRA o a MinAgricultura según `serie_fuente`. Ver
  `docs/licenses/data_licenses.md`.
- **Extractor**: `src/extractors/agro_eva_extractor.py`.
- **Filas esperadas**: 372 800 (166 732 + 206 068), confirmado en vivo el
  2026-11-27. 1109 municipios de 32 departamentos.

## Esquema

| Columna | Tipo | Descripción |
|---|---|---|
| `cod_dpto` | string (2 dígitos) | Código DIVIPOLA del departamento. **Nunca convertir a int** — ver Limitaciones sobre el cero inicial en la serie MinAgricultura. |
| `nombre_dpto` | string | Nombre del departamento tal cual la fuente (mayúsculas sin tildes en MinAgricultura, "Antioquia" en UPRA). |
| `cod_mpio` | string (5 dígitos) | Código DIVIPOLA del municipio — join key hacia `municipios`. **Nunca convertir a int.** |
| `nombre_mpio` | string | Nombre del municipio tal cual la fuente. Para joins usa `cod_mpio`, no el nombre. |
| `grupo_cultivo` | string | Grupo de cultivo tal cual la fuente. **No es comparable entre series** — ver Limitaciones. |
| `subgrupo_cultivo` | string | Subgrupo tal cual la fuente. **No es comparable entre series**: en MinAgricultura suele repetir el cultivo ("ACELGA"); en UPRA es una categoría ("Hortalizas de hoja"). |
| `cultivo` | string | Cultivo tal cual la fuente ("Acelga" en UPRA, "ACELGA" en MinAgricultura). |
| `cultivo_clean` | string | `cultivo` en minúsculas, sin tildes ni caracteres especiales ("acelga") — **usa esta columna para filtrar un cultivo a lo largo de 2006-2025**. |
| `desagregacion_cultivo` | string | Variedad o desagregación regional del cultivo (ej. "ACHIN" para malanga). |
| `anio` | int | Año de la evaluación. |
| `periodo` | string | `"2021"` (cultivo anual o permanente) o `"2021A"`/`"2021B"` (semestre, cultivos transitorios). Siempre empieza por `anio`. |
| `area_sembrada_ha` | float | Área sembrada, en hectáreas. |
| `area_cosechada_ha` | float | Área cosechada, en hectáreas. |
| `produccion_t` | float | Producción, en toneladas. |
| `rendimiento_t_ha` | float, nullable | Rendimiento en toneladas por hectárea, tal cual lo publica la fuente (no recalculado). Nulo solo cuando `area_cosechada_ha` = 0 en la serie MinAgricultura — ver Limitaciones. |
| `ciclo_cultivo` | string | Ciclo tal cual la fuente (ej. "Transitorio", "Permanente", "ANUAL"). |
| `estado_fisico_cultivo` | string | Estado físico de la producción reportada (ej. "En fresco", "FRUTO FRESCO", "SEMILLA"). |
| `codigo_cultivo` | string, nullable | Código del cultivo de UPRA. **Nulo en toda la serie MinAgricultura**, que no lo publica. |
| `nombre_cientifico_cultivo` | string, nullable | Nombre científico del cultivo (2857 nulos en la serie MinAgricultura). |
| `serie_fuente` | string | De qué serie viene la fila: `upra_2019_2025` o `minagricultura_2006_2018`. Define la atribución de la fila. |

Clave primaria: `(cod_mpio, cultivo, desagregacion_cultivo, periodo)` —
única en cada serie (confirmado en vivo con `$group`/`$having` sobre ambos
recursos) y validada en cada build.

## Uso

```python
import polars as pl
from colombia_open import ColombiaOpen

hub = ColombiaOpen()
eva = hub.load_polars("agro_eva")

# Producción nacional de papa por año, 2006-2025 (las dos series juntas)
(
    eva.filter(pl.col("cultivo_clean") == "papa")
    .group_by("anio")
    .agg(pl.col("produccion_t").sum().alias("toneladas"))
    .sort("anio")
)

# Los 10 municipios con más área cosechada en 2024
(
    eva.filter(pl.col("anio") == 2024)
    .group_by(["cod_mpio", "nombre_mpio"])
    .agg(pl.col("area_cosechada_ha").sum().alias("ha"))
    .sort("ha", descending=True)
    .head(10)
)

# Rendimiento homogéneo entre series: recalcúlalo en vez de promediar la columna
(
    eva.filter(pl.col("cultivo_clean") == "cafe")
    .group_by("anio")
    .agg((pl.col("produccion_t").sum() / pl.col("area_cosechada_ha").sum()).alias("t_ha"))
    .sort("anio")
)
```

## Limitaciones conocidas

- **Dos series, dos metodologías.** La transición MinAgricultura → UPRA en
  2019 cambia la taxonomía de cultivos. Un salto en 2018→2019 puede ser
  metodológico, no agronómico — compara con cuidado a través de ese corte y
  usa `serie_fuente` para separarlas.
- **`grupo_cultivo` no es comparable entre series.** UPRA usa 8 grupos
  (Cereales, Frutales, Hortalizas, Leguminosas, Oleaginosas, Raíces y
  tubérculos, Cultivos tropicales tradicionales, Cultivos para condimentos…);
  MinAgricultura usa 13, incluidos FIBRAS, FLORES Y FOLLAJES, FORESTALES y
  HONGOS, que no existen en UPRA, y "TUBERCULOS Y PLATANOS" no equivale a
  "Raíces y tubérculos". No se publica un mapeo entre ambas taxonomías: no
  hay uno oficial y fabricarlo sería inventar equivalencias.
- **Nombres de cultivo: coinciden la mayoría, no todos.** `cultivo_clean`
  resuelve la diferencia de mayúsculas/tildes (140 de los 165 cultivos de
  UPRA tienen el mismo nombre limpio en MinAgricultura). El resto cambió de
  nombre o se agrupó distinto entre series — ej. MinAgricultura distingue
  "CAÑA PANELERA", "CAÑA AZUCARERA" y otras cañas donde UPRA publica un
  solo "Caña"; "CALABACIN" y "CALABAZA" son, en UPRA, "Calabacín,
  calabaza". `cultivo_clean` no los une.
- **Rendimiento con dos convenciones cuando no hay cosecha.** Si
  `area_cosechada_ha` = 0, UPRA publica `rendimiento_t_ha` = 0.00 y
  MinAgricultura no publica el campo (3433 filas, nulo aquí). Esas filas se
  conservan — son pérdida de cosecha real (ej. 500 ha de malanga sembradas,
  0 cosechadas) — y no se imputa 0. Para series comparables, recalcula el
  rendimiento como `produccion_t / area_cosechada_ha` agregado (ver Uso).
- **929 filas con rendimiento > 0 pero área cosechada = 0** (serie
  MinAgricultura). Defecto de captura de la fuente: el rendimiento no
  corresponde a la producción reportada. Se publican tal cual; el validador
  las reporta como warning.
- **13 273 filas con área cosechada mayor que la sembrada**, casi todas en
  cultivos transitorios de la serie UPRA (13 203 de las 13 208 de UPRA). Es
  compatible con cosechar en un semestre área sembrada el semestre anterior,
  pero también hay casos que lucen a error de captura (ej. haba: 0.15 ha
  sembradas, 30 cosechadas). No se pudo distinguir uno de otro con el dato
  publicado: se publican sin corregir y el validador los reporta como
  warning.
- **Cero inicial perdido en la fuente MinAgricultura.** `c_d_dep`/`c_d_mun`
  están tipados como número en Socrata: Antioquia llega como `5` y Marinilla
  como `5440`. El extractor restaura el ancho fijo (`05`, `05440`) y el
  validador falla el build si algún código no tiene 2/5 dígitos. Si lees el
  recurso original directo, ten en cuenta este defecto.
- **Sin Bogotá, D.C.** Ninguna de las dos series reporta el departamento 11:
  la EVA no tiene producción agrícola registrada para Bogotá.
- **Discrepancia de `cod_mpio` con `municipios` (DIVIPOLA)** — el validador
  reporta cualquier `cod_mpio` que no exista en el `municipios` vigente
  como warning, no como error (0 casos en el build del 2026-11-27).
