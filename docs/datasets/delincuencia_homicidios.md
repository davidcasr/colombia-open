# delincuencia_homicidios

Víctimas de homicidio (incluido el feminicidio) por municipio y día, con
la zona, el sexo de la víctima, el arma o medio empleado y la modalidad
presunta. De 2003 a la fecha de corte más reciente de la fuente.

- **Fuente**: Ministerio de Defensa Nacional (datos de la Policía Nacional)
  — dataset "HOMICIDIO", vía la API Socrata de datos.gov.co:
  <https://www.datos.gov.co/resource/m8fd-ahd9.json>
- **Licencia**: CC BY-SA 4.0 (explícita en el portal, atribución a
  MinDefensa) — ver `docs/licenses/data_licenses.md`.
- **Extractor**: `src/extractors/delincuencia_homicidios_extractor.py`.
- **Filas esperadas**: ~286469 (345195 filas crudas en la fuente el
  2026-11-12, agregadas por combinación única — ver Granularidad),
  2003-01-01 a 2026-09-30, 345917 víctimas en 1108 municipios.

La fuente mide el homicidio **en víctimas**, no en hechos ni en denuncias:
un hecho con varias víctimas suma varias en `cantidad`.

## Granularidad

La fuente es casi microdato: una fila por víctima en la gran mayoría de
los casos (`cantidad` entre 1 y 38), y **las filas se repiten** — la misma
fecha, municipio y combinación de zona, sexo, arma, modalidad y
caracterización aparece varias veces.

Se publica **con todas las dimensiones de la fuente**, igual que
`delincuencia_hurto_modalidades`: una fila por fecha + `cod_mpio` + `zona`
+ `sexo` + `arma_medio` + `modalidad_presunta` + `caracterizacion`, con
`cantidad` sumada. No se pierde ninguna víctima ni ninguna dimensión. Los
días sin víctimas **no aparecen como fila con cero**.

Para series por municipio, agrupa y suma `cantidad` — nunca cuentes filas:
un mismo día y municipio tiene una fila por cada combinación de
dimensiones.

## Esquema

| Columna | Tipo | Descripción |
|---|---|---|
| `fecha` | date | Fecha del hecho (`fecha_hecho` en la fuente). |
| `anio` | int | Año de `fecha` — derivado, para joins con datasets anuales como `demografia`. |
| `cod_dpto` | string (2 dígitos) | Código DIVIPOLA de departamento (`cod_depto` en la fuente). **Nunca convertir a int.** |
| `nombre_dpto` | string | Nombre del departamento como lo entrega la fuente ("ANTIOQUIA", "BOGOTA D.C."…) — el más frecuente para ese `cod_dpto`. |
| `cod_mpio` | string (5 dígitos) | Código DIVIPOLA de municipio (`cod_muni` en la fuente) — join key hacia `municipios`. **Nunca convertir a int.** |
| `nombre_mpio` | string | Nombre del municipio como lo entrega la fuente, sin un sufijo " (CT)" si lo trae — el más frecuente para ese `cod_mpio`. Para joins usa `cod_mpio`. |
| `zona` | string | "URBANA" o "RURAL" (únicos 2 valores observados). |
| `sexo` | string | Sexo de la víctima, tal cual la fuente: "MASCULINO", "FEMENINO", "NO REPORTA", "SIN ESTABLECER". |
| `arma_medio` | string | Arma o medio empleado (`arma_medio`), tal cual la fuente: "ARMA DE FUEGO", "ARMA BLANCA / CORTOPUNZANTE", "CONTUNDENTES", "MINA ANTIPERSONA"… (43 valores observados). Nulo cuando la fuente no trae valor (296 filas agregadas) — no se rellena. |
| `modalidad_presunta` | string | Modalidad presunta (`_modalidad_presunta`), tal cual la fuente: "SICARIATO", "RIÑAS", "ATRACO", "VIOLENCIA INTRAFAMILIAR"… (69 valores observados). Nulo cuando la fuente no trae valor (2087 filas agregadas) — no se rellena. |
| `caracterizacion` | string | Caracterización SPOA (`spoa_caracterizacion`): "HOMICIDIO INTENCIONAL O CON DOLO" o "FEMINICIDIO" (únicos 2 valores observados). |
| `cantidad` | int | Número de víctimas para esa combinación (siempre > 0). |

Clave primaria: `(fecha, cod_mpio, zona, sexo, arma_medio,
modalidad_presunta, caracterizacion)` — garantizada única por la
agregación del extractor y validada en cada build. `arma_medio` y
`modalidad_presunta` pueden ser nulos dentro de la clave.

## Uso

```python
import polars as pl
from colombia_open import ColombiaOpen

hub = ColombiaOpen()
homicidios = hub.load_polars("delincuencia_homicidios")

# Víctimas de homicidio por año, en Cali
(
    homicidios.filter(pl.col("cod_mpio") == "76001")
    .group_by("anio")
    .agg(pl.col("cantidad").sum())
    .sort("anio")
)

# Feminicidios por año, nacional
(
    homicidios.filter(pl.col("caracterizacion") == "FEMINICIDIO")
    .group_by("anio")
    .agg(pl.col("cantidad").sum())
    .sort("anio")
)

# Tasa de homicidios por 100 mil habitantes: join con demografia
poblacion = hub.load_polars("demografia").filter(pl.col("area_geografica") == "Total")
(
    homicidios.group_by(["cod_mpio", "anio"])
    .agg(pl.col("cantidad").sum())
    .join(poblacion.select(["cod_mpio", "anio", "poblacion"]), on=["cod_mpio", "anio"])
    .with_columns((pl.col("cantidad") / pl.col("poblacion") * 100_000).alias("tasa_100k"))
)
```

`demografia` cubre 2018-2042, así que las tasas solo se pueden calcular
desde 2018.

## Limitaciones conocidas

- **Solo homicidio.** Los demás delitos de la misma familia de MinDefensa
  (homicidio en accidente de tránsito, masacres, delitos sexuales,
  violencia intrafamiliar, extorsión, secuestro, hurto a vehículos,
  abigeato, terrorismo, piratería terrestre) son endpoints distintos y no
  están en este dataset — ver `docs/roadmap/roadmap.md` e issue #29.
- **Feminicidio dentro del mismo dataset.** La fuente lo trae como una
  caracterización SPOA más (`caracterizacion == "FEMINICIDIO"`, 1919
  víctimas al 2026-11-12), no como un conjunto aparte. Los homicidios de
  mujeres no caracterizados como feminicidio siguen como "HOMICIDIO
  INTENCIONAL O CON DOLO".
- **Valores de texto sin homologar.** `arma_medio` y `modalidad_presunta`
  se publican tal cual la fuente: hay categorías que se solapan
  ("ARMA BLANCA / CORTOPUNZANTE" y "CORTOPUNZANTES"; "NO REPORTADO",
  "SIN ESTABLECER" y nulo) y no se fusionan aquí — eso sería una decisión
  de interpretación que no le corresponde al dataset.
- **Agregación respecto a la fuente cruda**: 345195 filas crudas colapsan
  a ~286469 filas publicadas. Para el total de víctimas, suma `cantidad` —
  no cuentes filas.
- **Filas sin municipio**: hoy la fuente no trae ninguna (confirmado el
  2026-11-12). Si aparecen (código ausente o no numérico, como el
  "SIN ESTABLECER" de `delincuencia_hurto_personas`), el extractor las
  excluye — no fabrica un código — y su conteo queda en las `notes` de la
  metadata de staging de cada build.
- **La serie no es homogénea en el tiempo.** Las categorías de modalidad
  y arma cambian con las prácticas de registro de la Policía (p. ej. en
  2003 ~64% de las víctimas tienen modalidad "NO REPORTADA").
- **El año en curso está incompleto**: la fuente se actualiza con corte
  mensual (último corte observado: 2026-09-30).
- **Discrepancia de `cod_mpio` con `municipios` (DIVIPOLA)** — igual que en
  los demás datasets de entidades distintas al DANE: el validador reporta
  cualquier `cod_mpio` que no exista en el `municipios` vigente como
  warning, no como error.
- **Cifras distintas a Medicina Legal.** Las cifras de homicidio de la
  Policía y las del Instituto Nacional de Medicina Legal no coinciden
  exactamente (fuentes y criterios de registro distintos). Este dataset
  es solo la cifra de la Policía.
