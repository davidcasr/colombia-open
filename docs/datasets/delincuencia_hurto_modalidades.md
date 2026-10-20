# delincuencia_hurto_modalidades

Víctimas de hurto por modalidades — residencias y entidades comerciales —
por municipio y día, con el arma o medio empleado, y el género y grupo
etario de la víctima. De 2010 a la fecha de corte más reciente de la
fuente.

- **Fuente**: Policía Nacional (Dirección General — DIPON), dataset
  "Reporte Hurto por Modalidades Policía Nacional", vía la API Socrata de
  datos.gov.co: <https://www.datos.gov.co/resource/6sqw-8cg5.json>
- **Licencia**: CC BY-SA 4.0 (explícita en el portal, atribución a la
  Policía Nacional) — ver `docs/licenses/data_licenses.md`.
- **Extractor**: `src/extractors/delincuencia_hurto_modalidades_extractor.py`.
- **Filas esperadas**: ~397361 (653384 en la fuente el 2026-10-20, tras
  colapsar centro poblado a municipio y excluir 1 fila sin municipio — ver
  Granularidad y Limitaciones), 2010-01-01 a 2026-07-31, 653383 hechos.

## Granularidad

La fuente trae una fila por fecha + centro poblado + tipo de hurto +
arma/medio + género + grupo etario, con `cantidad` siempre en "1" (un
hecho = un registro). Su `codigo_dane` tiene 8 dígitos: los 5 primeros son
el municipio DIVIPOLA y los 3 últimos el centro poblado (`000` = cabecera
municipal).

Se publica **con todas las dimensiones de la fuente, pero colapsando el
centro poblado a municipio**: una fila por fecha + `cod_mpio` +
`tipo_hurto` + `arma_medio` + `genero` + `grupo_etario`, con `cantidad`
sumada. No hay hoy en `colombia-open` un dataset de centros poblados con
el cual hacer join con los 3 dígitos finales. Los días sin hechos **no
aparecen como fila con cero**.

Para series por municipio, agrupa y suma `cantidad` — nunca cuentes filas:
una misma fecha y municipio tiene una fila por cada combinación de
tipo de hurto, arma, género y grupo etario.

## Esquema

| Columna | Tipo | Descripción |
|---|---|---|
| `fecha` | date | Fecha del hecho (`fecha_hecho` en la fuente, `dd/mm/aaaa`). |
| `anio` | int | Año de `fecha` — derivado, para joins con datasets anuales como `demografia`. |
| `cod_dpto` | string (2 dígitos) | Código DIVIPOLA de departamento (2 primeros dígitos de `codigo_dane`). **Nunca convertir a int.** |
| `nombre_dpto` | string | Nombre del departamento como lo entrega la fuente ("ANTIOQUIA", "BOGOTA", "VALLE DEL CAUCA"…) — el más frecuente para ese `cod_dpto`. |
| `cod_mpio` | string (5 dígitos) | Código DIVIPOLA de municipio (5 primeros dígitos de `codigo_dane`) — join key hacia `municipios`. **Nunca convertir a int.** |
| `nombre_mpio` | string | Nombre del municipio, sin el sufijo " (CT)" con el que la fuente marca las capitales — el más frecuente para ese `cod_mpio`. Para joins usa `cod_mpio`. |
| `tipo_hurto` | string | Modalidad tal como la reporta la fuente (`tipo_de_hurto`): "ARTÍCULO 239. HURTO RESIDENCIAS" o "ARTÍCULO 239. HURTO ENTIDADES COMERCIALES" (únicos 2 valores observados). |
| `modalidad` | string | **Derivado** de `tipo_hurto`: `residencias` o `comercio`. Nulo si la fuente reporta un texto no mapeado (el validador lo avisa como warning). |
| `arma_medio` | string | Arma o medio empleado (`armas_medios`), tal cual la fuente: "CONTUNDENTES", "LLAVE MAESTRA", "ESCOPOLAMINA", "SIN EMPLEO DE ARMAS", "NO REPORTADO"… (11 valores observados). |
| `genero` | string | Género de la víctima: "MASCULINO", "FEMENINO", "NO REPORTA". Nulo en ~53% de las filas agregadas (la fuente no reporta género en la mayoría de los hechos) — no se rellena. |
| `grupo_etario` | string | "ADULTOS", "ADOLESCENTES" o "MENORES". Nulo cuando la fuente no trae valor — no se rellena. |
| `cantidad` | int | Número de hechos para esa combinación (siempre > 0). |

Clave primaria: `(fecha, cod_mpio, tipo_hurto, arma_medio, genero,
grupo_etario)` — garantizada única por la agregación del extractor y
validada en cada build. `genero` y `grupo_etario` pueden ser nulos dentro
de la clave.

## Uso

```python
import polars as pl
from colombia_open import ColombiaOpen

hub = ColombiaOpen()
modalidades = hub.load_polars("delincuencia_hurto_modalidades")

# Hurto a residencias por año, en Medellín
(
    modalidades.filter((pl.col("cod_mpio") == "05001") & (pl.col("modalidad") == "residencias"))
    .group_by("anio")
    .agg(pl.col("cantidad").sum())
    .sort("anio")
)

# Hechos por modalidad y arma/medio, nacional, 2025
(
    modalidades.filter(pl.col("anio") == 2025)
    .group_by(["modalidad", "arma_medio"])
    .agg(pl.col("cantidad").sum())
    .sort("cantidad", descending=True)
)

# Tasa de hurto a comercios por 100 mil habitantes: join con demografia
poblacion = hub.load_polars("demografia").filter(pl.col("area_geografica") == "Total")
(
    modalidades.filter(pl.col("modalidad") == "comercio")
    .group_by(["cod_mpio", "anio"])
    .agg(pl.col("cantidad").sum())
    .join(poblacion.select(["cod_mpio", "anio", "poblacion"]), on=["cod_mpio", "anio"])
    .with_columns((pl.col("cantidad") / pl.col("poblacion") * 100_000).alias("tasa_100k"))
)
```

`demografia` cubre 2018-2042, así que las tasas solo se pueden calcular
desde 2018.

## Limitaciones conocidas

- **Solo dos modalidades.** A diferencia de lesiones personales (12
  conductas), esta fuente cubre únicamente hurto a residencias y a
  entidades comerciales — no incluye hurto a personas (dataset separado,
  `delincuencia_hurto_personas`) ni otras modalidades (vehículos,
  motocicletas, abigeato, etc.), que la Policía no publica en este
  endpoint.
- **1 fila sin municipio excluida.** Confirmado en vivo el 2026-10-20: 1
  fila trae `codigo_dane` = "00000000" pese a traer nombre de departamento
  y municipio en texto. Se excluye — no se fabrica un código — y el
  conteo queda en las `notes` de la metadata de staging de cada build.
- **`genero` es mayoritariamente nulo** (~53% de las filas agregadas, ~89%
  de las filas crudas de la fuente) — a diferencia de lesiones personales,
  donde el género casi siempre se reporta. No se rellena ni se infiere.
- **Agregación fuerte respecto a la fuente cruda**: 653384 filas crudas
  (cantidad siempre "1") colapsan a ~397361 filas publicadas, porque
  muchos hechos comparten la misma combinación de fecha + municipio +
  modalidad + arma + género + grupo etario (especialmente cuando género y
  grupo etario son nulos). Para el total de hechos, suma `cantidad` — no
  cuentes filas.
- **Centro poblado no publicado.** Los 3 últimos dígitos de `codigo_dane`
  se descartan al agregar a municipio (ver Granularidad).
- **La serie no es homogénea en el tiempo.** El volumen de hechos cambia
  con prácticas de registro y denuncia, no solo con la criminalidad real.
- **El año en curso está incompleto**: la fuente se actualiza con corte
  mensual (último corte observado: 2026-07-31).
- **Discrepancia de `cod_mpio` con `municipios` (DIVIPOLA)** — igual que en
  los demás datasets de entidades distintas al DANE: el validador reporta
  cualquier `cod_mpio` que no exista en el `municipios` vigente como
  warning, no como error.
