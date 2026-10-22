# calidad_aire

Calidad del aire por estación de monitoreo — los 6 contaminantes del
Índice de Calidad del Aire (ICA) colombiano, promedio anual. 2011 a la
fecha.

- **Fuente**: IDEAM — "Calidad del Aire en Colombia (Promedio Anual)"
  (`kekd-7v7h`), vía la API Socrata de datos.gov.co:
  <https://www.datos.gov.co/resource/kekd-7v7h.json>. Reemplaza la pista
  original del roadmap (SISAIRE directo — nunca se encontró una API
  pública confirmable para ese portal).
- **Licencia**: CC BY-SA 4.0 (explícita en el portal, atribución al
  IDEAM) — ver `docs/licenses/data_licenses.md`.
- **Extractor**: `src/extractors/calidad_aire_extractor.py`.
- **Filas esperadas**: ~8985 (de 30665 filas totales en la fuente; 15625
  tras filtrar a los 6 contaminantes ICA, menos 4 sin código de municipio,
  colapsadas a ~8985 porque la fuente publica buena parte de las filas
  dos veces — ver "Calidad de dato" abajo — confirmado en vivo el
  2026-10-22).

## Decisión de alcance: solo contaminantes, no meteorología

La fuente mezcla 20 "variable" distintas en una sola tabla: 6
contaminantes reales y 14 variables meteorológicas (temperatura, humedad,
viento, lluvia, radiación), más PST (partículas suspendidas totales,
métrica legacy superada por PM10/PM2.5 en la normativa actual) y NO
(precursor de NO2, no es en sí un contaminante del ICA).

**Se publican solo los 6 contaminantes del Índice de Calidad del Aire
colombiano** (Resolución 2254 de 2017): `PM10`, `PM2.5`, `SO2`, `O3`,
`NO2`, `CO`. Las variables meteorológicas, PST y NO quedan fuera de esta
primera iteración — candidatas a una segunda si hay demanda, documentadas
aquí en vez de implementadas especulativamente.

## Granularidad

Una fila por **estación + contaminante + ventana de exposición + año**.
La fuente reporta más de una ventana de exposición por contaminante (ej.
PM10 a 1h y a 24h, O3 a 1h y a 8h) — **no se colapsa a una sola ventana**,
se publican todas tal como las reporta la fuente. Si necesitas el valor
"oficial" del ICA, filtra por la ventana estándar de cada contaminante:

| Contaminante | Ventana estándar ICA |
|---|---|
| PM10, PM2.5, SO2 | 24 horas |
| O3, CO | 8 horas |
| NO2 | 1 hora |

## Calidad de dato: la fuente publica la misma fila dos veces

Confirmado en vivo el 2026-10-22 contra la respuesta HTTP cruda (no es un
artefacto de este extractor): ~6636 de las ~15600 combinaciones
estación+contaminante+ventana+año vienen **publicadas dos veces** en la
fuente. Casi siempre (más del 99% de los pares) con el mismo valor pero
formateado distinto — ej. `c_digo_del_municipio` "68001" en una copia y
"68001.0" en la otra, lo que de paso explica la inconsistencia de
mayúsculas en los nombres (ver Limitaciones). En una fracción pequeña de
los pares (~1%) el `promedio` reportado en cada copia además **difiere
genuinamente**, no solo el formato — en ese caso se publica el promedio
de las dos copias, nunca se descarta el grupo ni se fabrica un tercer
valor. El conteo de combinaciones colapsadas queda en las `notes` de la
metadata de staging de cada build.

## Esquema

| Columna | Tipo | Descripción |
|---|---|---|
| `id_estacion` | string | Identificador de la estación de monitoreo — clave primaria junto con `contaminante`, `tiempo_exposicion_horas` y `anio`. |
| `nombre_estacion` | string, nullable | Nombre de la estación. |
| `autoridad_ambiental` | string, nullable | CAR/entidad que opera la estación (ej. "AMVA", "CORPOCESAR"). |
| `tipo_estacion` | string, nullable | "Fija" u otro tipo reportado por la fuente. |
| `cod_dpto` | string (2 dígitos) | Código DIVIPOLA de departamento. **Nunca convertir a int** — la fuente lo entrega inconsistente (a veces "5", a veces "5.0") y se normaliza siempre a ancho fijo. |
| `nombre_dpto` | string, nullable | Nombre del departamento — el más frecuente para ese `cod_dpto` (ver Limitaciones: la fuente trae mayúsculas inconsistentes). |
| `cod_mpio` | string (5 dígitos) | Código DIVIPOLA de municipio — join key hacia `municipios`. **Nunca convertir a int.** |
| `nombre_mpio` | string, nullable | Nombre del municipio — el más frecuente para ese `cod_mpio`. |
| `latitud` / `longitud` | float | Ubicación de la estación, EPSG:4326. |
| `anio` | int | Año del promedio. |
| `contaminante` | string | Uno de `PM10`, `PM2.5`, `SO2`, `O3`, `NO2`, `CO`. |
| `tiempo_exposicion_horas` | int | Ventana de exposición del promedio (1, 3, 8 o 24 horas según el contaminante). |
| `unidad` | string, nullable | Siempre "ugm3" (µg/m³) para los 6 contaminantes publicados. |
| `promedio` | float | Promedio anual — siempre > 0. |
| `mediana` | float, nullable | Mediana anual. |
| `maximo` | float, nullable | Valor máximo registrado en el año. |
| `no_de_datos` | int, nullable | Número de lecturas horarias que sustentan el promedio. |
| `representatividad_temporal` | float, nullable | % del año cubierto por datos válidos — debería estar en [0, 100] (warning si no). |
| `dias_excedencia` | int, nullable | Días del año en que se excedió el límite normativo vigente. |
| `porcentaje_excedencia` | float, nullable | % de mediciones que excedieron el límite. |

## Uso

```python
import polars as pl
from colombia_open import ColombiaOpen

hub = ColombiaOpen()
aire = hub.load_polars("calidad_aire")

# PM2.5 (ventana ICA estándar: 24h) por municipio, último año disponible
ultimo_anio = aire["anio"].max()
(
    aire.filter(
        (pl.col("contaminante") == "PM2.5")
        & (pl.col("tiempo_exposicion_horas") == 24)
        & (pl.col("anio") == ultimo_anio)
    )
    .group_by(["cod_mpio", "nombre_mpio"])
    .agg(pl.col("promedio").mean().round(1).alias("pm25_promedio"))
    .sort("pm25_promedio", descending=True)
    .head(10)
)

# Evolución de PM10 (24h) en una estación específica
aire.filter(
    (pl.col("id_estacion") == "9020")
    & (pl.col("contaminante") == "PM10")
    & (pl.col("tiempo_exposicion_horas") == 24)
).sort("anio").select(["anio", "promedio", "dias_excedencia"])
```

## Limitaciones conocidas

- **Solo 6 de 20 "variable" de la fuente** — ver "Decisión de alcance"
  arriba. Si necesitas temperatura, humedad, viento, lluvia o radiación,
  esos datos existen en la fuente cruda pero no se publican aquí.
- **No colapsa ventanas de exposición** — un mismo contaminante puede
  tener varias filas por estación-año (una por ventana). Filtra por la
  ventana estándar ICA si quieres el valor "oficial" (ver tabla arriba).
- **Nivel de estación, no de municipio** — varios municipios grandes
  tienen más de una estación; si quieres un solo valor por municipio,
  agrega tú mismo (`group_by(["cod_mpio", "anio", "contaminante"])`).
- **513 estaciones, cobertura geográfica desigual** — zonas rurales y
  municipios pequeños probablemente no tengan ninguna estación.
- **4 filas excluidas** por no traer código de municipio en la fuente — no
  se fabrica un valor de reemplazo.
- **`nombre_del_departamento`/`nombre_del_municipio` traen mayúsculas
  inconsistentes en la fuente** para el mismo código (ej. "ANTIOQUIA" en
  unas filas, "Antioquia" en otras — confirmado en vivo: 20 de 33
  departamentos y 103 municipios afectados). `nombre_dpto`/`nombre_mpio`
  publican el valor más frecuente por código, no el de cada fila — para
  agrupar o filtrar por lugar, usa siempre `cod_dpto`/`cod_mpio`, nunca el
  nombre como texto libre.
- **Discrepancia de `cod_mpio` con `municipios` (DIVIPOLA)** — igual que
  el resto del catálogo: IDEAM y DANE son entidades distintas con ciclos
  de actualización propios. El validador reporta cualquier `cod_mpio` que
  no exista en `municipios` vigente como warning, no error.
