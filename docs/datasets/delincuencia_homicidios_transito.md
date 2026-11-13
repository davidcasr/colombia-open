# delincuencia_homicidios_transito

Víctimas de homicidio en accidente de tránsito por municipio y día, de
2003 a la fecha de corte más reciente de la fuente.

- **Fuente**: Ministerio de Defensa Nacional (datos de la Policía Nacional)
  — dataset "HOMICIDIO EN ACCIDENTE DE TRÁNSITO", vía la API Socrata de
  datos.gov.co: <https://www.datos.gov.co/resource/uav5-b85g.json>
- **Licencia**: CC BY-SA 4.0 (explícita en el portal, atribución a
  MinDefensa) — ver `docs/licenses/data_licenses.md`.
- **Extractor**: `src/extractors/delincuencia_homicidios_transito_extractor.py`.
- **Filas esperadas**: ~102336 (128440 filas crudas en la fuente el
  2026-11-13, agregadas por fecha y municipio — ver Granularidad),
  2003-01-01 a 2026-09-30, 128900 víctimas en 1077 municipios.

La fuente mide **víctimas** (personas muertas en un hecho de tránsito
registrado como homicidio), no accidentes ni denuncias: un mismo accidente
con varias víctimas suma varias en `cantidad`.

## Granularidad

La fuente trae solo fecha, municipio y `cantidad` — ninguna otra
dimensión. Pero las filas **no son únicas por `(fecha, municipio)`**: es
casi microdato (una fila ≈ una víctima, `cantidad` entre 1 y 11) y 17954
combinaciones de fecha y municipio aparecen repetidas.

Se publica **una fila por fecha + `cod_mpio`**, con `cantidad` sumada —
mismo esquema y misma clave que `delincuencia_hurto_personas`. No se
pierde ninguna víctima. Los días sin víctimas **no aparecen como fila con
cero**.

## Esquema

| Columna | Tipo | Descripción |
|---|---|---|
| `fecha` | date | Fecha del hecho (`fecha_hecho` en la fuente). |
| `anio` | int | Año de `fecha` — derivado, para joins con datasets anuales como `demografia`. |
| `cod_dpto` | string (2 dígitos) | Código DIVIPOLA de departamento (`cod_depto` en la fuente). **Nunca convertir a int.** |
| `nombre_dpto` | string | Nombre del departamento como lo entrega la fuente ("ANTIOQUIA", "BOGOTA D.C."…) — el más frecuente para ese `cod_dpto`. |
| `cod_mpio` | string (5 dígitos) | Código DIVIPOLA de municipio (`cod_muni` en la fuente) — join key hacia `municipios`. **Nunca convertir a int.** |
| `nombre_mpio` | string | Nombre del municipio como lo entrega la fuente, sin un sufijo " (CT)" si lo trae — el más frecuente para ese `cod_mpio`. Para joins usa `cod_mpio`. |
| `cantidad` | int | Número de víctimas ese día en ese municipio (siempre > 0). |

Clave primaria: `(fecha, cod_mpio)` — garantizada única por la agregación
del extractor y validada en cada build.

## Uso

```python
import polars as pl
from colombia_open import ColombiaOpen

hub = ColombiaOpen()
transito = hub.load_polars("delincuencia_homicidios_transito")

# Víctimas de homicidio en tránsito por año, nacional
transito.group_by("anio").agg(pl.col("cantidad").sum()).sort("anio")

# Tasa por 100 mil habitantes: join con demografia
poblacion = hub.load_polars("demografia").filter(pl.col("area_geografica") == "Total")
(
    transito.group_by(["cod_mpio", "anio"])
    .agg(pl.col("cantidad").sum())
    .join(poblacion.select(["cod_mpio", "anio", "poblacion"]), on=["cod_mpio", "anio"])
    .with_columns((pl.col("cantidad") / pl.col("poblacion") * 100_000).alias("tasa_100k"))
)

# Junto a los homicidios intencionales: mismas llaves (fecha, cod_mpio)
homicidios = hub.load_polars("delincuencia_homicidios")
(
    homicidios.group_by(["cod_mpio", "anio"]).agg(pl.col("cantidad").sum().alias("homicidios"))
    .join(
        transito.group_by(["cod_mpio", "anio"]).agg(pl.col("cantidad").sum().alias("transito")),
        on=["cod_mpio", "anio"],
        how="full",
        coalesce=True,
    )
)
```

`demografia` cubre 2018-2042, así que las tasas solo se pueden calcular
desde 2018.

## Limitaciones conocidas

- **Sin dimensiones.** La fuente no trae zona, sexo, edad, tipo de
  vehículo ni condición de la víctima (peatón, motociclista…): solo el
  conteo por día y municipio.
- **No es la cifra oficial de siniestralidad vial.** Es el registro de la
  Policía de homicidios (culposos) en accidentes de tránsito. La Agencia
  Nacional de Seguridad Vial y Medicina Legal publican cifras de
  fallecidos en siniestros viales con criterios distintos, que no
  coinciden exactamente con esta.
- **Separado de `delincuencia_homicidios`.** Ese dataset es homicidio
  intencional (y feminicidio); este es el homicidio en tránsito. Son
  endpoints distintos de la fuente y no se solapan. Las **lesiones** en
  tránsito están en `delincuencia_lesiones_personales`
  (`tipo_lesion`), no aquí.
- **Familia elegida.** Existe también una versión DIPON de este delito
  (`ha6j-pa2r`, formato de `delincuencia_lesiones_personales`, con
  `codigo_dane` de 8 dígitos). Se usó la de MinDefensa (`uav5-b85g`)
  porque cubre desde 2003 y comparte esquema con `delincuencia_homicidios`.
- **Agregación respecto a la fuente cruda**: 128440 filas crudas colapsan
  a ~102336 filas publicadas. Para el total de víctimas, suma `cantidad` —
  no cuentes filas.
- **Filas sin municipio**: hoy la fuente no trae ninguna (confirmado el
  2026-11-13). Si aparecen (código ausente o no numérico, como el
  "SIN ESTABLECER" de `delincuencia_hurto_personas`), el extractor las
  excluye — no fabrica un código — y su conteo queda en las `notes` de la
  metadata de staging de cada build.
- **El año en curso está incompleto**: la fuente se actualiza con corte
  mensual (último corte observado: 2026-09-30).
- **Discrepancia de `cod_mpio` con `municipios` (DIVIPOLA)** — igual que en
  los demás datasets de entidades distintas al DANE: el validador reporta
  cualquier `cod_mpio` que no exista en el `municipios` vigente como
  warning, no como error (al 2026-11-13 no hay ninguno).
