# delincuencia_lesiones_personales

Víctimas de lesiones personales — dolosas y culposas, incluidas las
lesiones en accidente de tránsito — por municipio y día, con la conducta
del Código Penal, el arma o medio empleado, y el género y grupo etario de
la víctima. De 2010 a la fecha de corte más reciente de la fuente.

- **Fuente**: Policía Nacional (Dirección General — DIPON), dataset
  "Reporte Lesiones Personales y en Accidente de Tránsito Policía
  Nacional", vía la API Socrata de datos.gov.co:
  <https://www.datos.gov.co/resource/72sg-cybi.json>
- **Licencia**: CC BY-SA 4.0 (explícita en el portal, atribución a la
  Policía Nacional) — ver `docs/licenses/data_licenses.md`.
- **Extractor**: `src/extractors/delincuencia_lesiones_personales_extractor.py`.
- **Filas esperadas**: ~1377323 (1381416 en la fuente el 2026-10-19, tras
  colapsar centro poblado a municipio y excluir 4 filas sin municipio — ver
  Granularidad y Limitaciones), 2010-01-01 a 2026-07-31, ~2.35 millones de
  víctimas.

## Granularidad

La fuente trae una fila por fecha + centro poblado + conducta + arma/medio
+ género + grupo etario, con `cantidad` = número de víctimas. Su
`codigo_dane` tiene 8 dígitos: los 5 primeros son el municipio DIVIPOLA y
los 3 últimos el centro poblado (`000` = cabecera municipal, ~99% de las
filas).

Se publica **con todas las dimensiones de la fuente, pero colapsando el
centro poblado a municipio**: una fila por fecha + `cod_mpio` + `conducta`
+ `arma_medio` + `genero` + `grupo_etario`, con `cantidad` sumada. No hay
hoy en `colombia-open` un dataset de centros poblados con el cual hacer
join con los 3 dígitos finales. Los días sin víctimas **no aparecen como
fila con cero**.

Para series por municipio, agrupa y suma `cantidad` — nunca cuentes filas:
una misma fecha y municipio tiene una fila por cada combinación de
conducta, arma, género y grupo etario.

## Esquema

| Columna | Tipo | Descripción |
|---|---|---|
| `fecha` | date | Fecha del hecho (`fecha_hecho` en la fuente, `dd/mm/aaaa`). |
| `anio` | int | Año de `fecha` — derivado, para joins con datasets anuales como `demografia`. |
| `cod_dpto` | string (2 dígitos) | Código DIVIPOLA de departamento (2 primeros dígitos de `codigo_dane`). **Nunca convertir a int.** |
| `nombre_dpto` | string | Nombre del departamento como lo entrega la fuente ("BOGOTA", "VALLE", "SAN ANDRÉS"…) — el más frecuente para ese `cod_dpto`. |
| `cod_mpio` | string (5 dígitos) | Código DIVIPOLA de municipio (5 primeros dígitos de `codigo_dane`) — join key hacia `municipios`. **Nunca convertir a int.** |
| `nombre_mpio` | string | Nombre del municipio, sin el sufijo " (CT)" con el que la fuente marca las capitales — el más frecuente para ese `cod_mpio`. Para joins usa `cod_mpio`. |
| `conducta` | string | Conducta tal como la reporta la fuente (`descripci_n_conducta`), p. ej. "ARTÍCULO 111. LESIONES PERSONALES". 12 valores observados (artículos 111-116, 119, 120, 125, 126 y 136 de la Ley 599 de 2000). |
| `tipo_lesion` | string | **Derivado** del artículo en `conducta`: `dolosa` (111-119, 125, 136), `culposa_transito` (art. 120 en accidente de tránsito) o `culposa_otra` (art. 120 fuera de tránsito, y art. 126). Nulo si la fuente reporta un artículo no mapeado (el validador lo avisa como warning). |
| `arma_medio` | string | Arma o medio empleado (`armas_medios`), tal cual la fuente: "CONTUNDENTES", "ARMA BLANCA / CORTOPUNZANTE", "VEHICULO", "SIN EMPLEO DE ARMAS", "NO REPORTADO"… (45 valores observados). |
| `genero` | string | Género de la víctima: "MASCULINO", "FEMENINO", "NO REPORTA". Nulo cuando la fuente no trae valor (~2100 filas) — no se rellena. |
| `grupo_etario` | string | "ADULTOS", "ADOLESCENTES" o "MENORES". Nulo cuando la fuente no trae valor (~800 filas) — no se rellena. |
| `cantidad` | int | Número de víctimas para esa combinación (siempre > 0). |

Clave primaria: `(fecha, cod_mpio, conducta, arma_medio, genero,
grupo_etario)` — garantizada única por la agregación del extractor y
validada en cada build. `genero` y `grupo_etario` pueden ser nulos dentro
de la clave.

## Uso

```python
import polars as pl
from colombia_open import ColombiaOpen

hub = ColombiaOpen()
lesiones = hub.load_polars("delincuencia_lesiones_personales")

# Solo lesiones intencionales (sin accidentes de tránsito), por año, en Cali
(
    lesiones.filter((pl.col("cod_mpio") == "76001") & (pl.col("tipo_lesion") == "dolosa"))
    .group_by("anio")
    .agg(pl.col("cantidad").sum())
    .sort("anio")
)

# Víctimas de lesiones dolosas por género y arma, nacional, 2025
(
    lesiones.filter((pl.col("anio") == 2025) & (pl.col("tipo_lesion") == "dolosa"))
    .group_by(["genero", "arma_medio"])
    .agg(pl.col("cantidad").sum())
    .sort("cantidad", descending=True)
)

# Tasa de lesiones en tránsito por 100 mil habitantes: join con demografia
poblacion = hub.load_polars("demografia").filter(pl.col("area_geografica") == "Total")
(
    lesiones.filter(pl.col("tipo_lesion") == "culposa_transito")
    .group_by(["cod_mpio", "anio"])
    .agg(pl.col("cantidad").sum())
    .join(poblacion.select(["cod_mpio", "anio", "poblacion"]), on=["cod_mpio", "anio"])
    .with_columns((pl.col("cantidad") / pl.col("poblacion") * 100_000).alias("tasa_100k"))
)
```

`demografia` cubre 2018-2042, así que las tasas solo se pueden calcular
desde 2018.

## Limitaciones conocidas

- **Mezcla delitos dolosos y accidentes de tránsito.** Aproximadamente un
  tercio de las víctimas (~755 mil) son lesiones culposas en accidente de
  tránsito. Filtra por `tipo_lesion` antes de hablar de "violencia" — si no,
  estarás sumando choques con riñas.
- **4 filas sin municipio excluidas.** Confirmado en vivo el 2026-10-19:
  4 filas (4 víctimas, 2010-2014) traen `codigo_dane` = "00000000". Se
  excluyen — no se fabrica un código — y el conteo queda en las `notes` de
  la metadata de staging de cada build.
- **Al menos ~25 filas tienen código y nombre contradictorios** en la fuente
  (ej. `25754001`, que es Soacha en Cundinamarca, con municipio "Jamundí" y
  departamento "VALLE"; o `25594002` = Quetame con "Yumbo"). No hay forma
  de saber cuál de los dos campos es el correcto; se confía en el código
  (la clave de join) y el nombre publicado por `cod_mpio` es el más
  frecuente para ese código en la fuente. El impacto en conteos es
  despreciable (~30 víctimas de 2.35 millones).
- **Centro poblado no publicado.** Los 3 últimos dígitos de `codigo_dane`
  se descartan al agregar a municipio (ver Granularidad).
- **`conducta` tiene variantes de texto en la fuente** — p. ej.
  "ARTICULO 120 LESIONES CULPOSAS" (sin tilde ni punto) coexiste con
  "ARTÍCULO 120. LESIONES CULPOSAS ( EN ACCIDENTE DE TRANSITO )". Son
  conductas distintas en la fuente y se publican tal cual; para agrupar,
  usa `tipo_lesion`.
- **La serie no es homogénea en el tiempo.** Los municipios con registros
  pasan de ~990 (2010) a ~1100 (2016 en adelante), y el volumen de
  víctimas cambia con prácticas de registro y denuncia, no solo con la
  criminalidad. 2020 cae por las restricciones de movilidad de la
  pandemia.
- **`culposa_otra` no es homogénea en el tiempo.** La etiqueta genérica
  "ARTICULO 120 LESIONES CULPOSAS" (sin "en accidente de tránsito") solo
  aparece entre 2017 y 2022 (~1300 víctimas en 2017, ~2600 en 2020, ~6400
  en 2021, ~2400 en 2022) y desaparece desde 2023; el resto de
  `culposa_otra` es el art. 126 (lesiones culposas al feto, <100 al año).
  Parece una codificación de la fuente en esos años, no un fenómeno real —
  para series largas de lesiones culposas, considera sumar
  `culposa_transito` + `culposa_otra`.
- **El año en curso está incompleto**: la fuente se actualiza con corte
  mensual (último corte observado: 2026-07-31).
- **Discrepancia de `cod_mpio` con `municipios` (DIVIPOLA)** — igual que en
  los demás datasets de entidades distintas al DANE: el validador reporta
  cualquier `cod_mpio` que no exista en el `municipios` vigente como
  warning, no como error.
- **Solo lesiones personales.** El hurto por modalidades (residencias y
  entidades comerciales) vive en un dataset separado:
  `delincuencia_hurto_modalidades`.
