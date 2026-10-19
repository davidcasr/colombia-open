# delincuencia_hurto_personas

Víctimas de hurto a personas por municipio y día, de 2003 a la fecha de
corte más reciente de la fuente.

- **Fuente**: Ministerio de Defensa Nacional (datos de la Policía Nacional)
  — dataset "HURTO PERSONAS", vía la API Socrata de datos.gov.co:
  <https://www.datos.gov.co/resource/4rxi-8m8d.json>
- **Licencia**: CC BY-SA 4.0 (explícita en el portal, atribución a
  MinDefensa) — ver `docs/licenses/data_licenses.md`.
- **Extractor**: `src/extractors/delincuencia_hurto_personas_extractor.py`.
- **Filas esperadas**: ~650835 (651200 en la fuente el 2026-10-19, menos
  365 filas sin municipio — ver limitaciones), 2003-01-01 a 2026-08-31.

La fuente define el hurto a personas como la "modalidad de hurto donde el
victimario utiliza diferentes medios con el fin de apoderarse de los
elementos de valor que lleva consigo una persona" y **lo mide en
víctimas**, no en denuncias ni en hechos.

## Granularidad

La fuente ya viene agregada: una fila por fecha + municipio, con el número
de víctimas de ese día. No es microdato por hecho (no trae sexo, edad,
arma, hora ni barrio). Se publica con la misma granularidad diaria, sin
re-agregar — si necesitas series mensuales o anuales, agrupa por `anio` o
por `fecha` truncada (ver Uso). Los días sin víctimas en un municipio **no
aparecen como fila con cero**: simplemente no hay fila.

## Esquema

| Columna | Tipo | Descripción |
|---|---|---|
| `fecha` | date | Fecha del hecho (`fecha_hecho` en la fuente). |
| `anio` | int | Año de `fecha` — derivado, para facilitar joins con datasets anuales como `demografia`. |
| `cod_dpto` | string (2 dígitos) | Código DIVIPOLA de departamento. **Nunca convertir a int.** |
| `nombre_dpto` | string | Nombre del departamento tal como lo entrega la fuente (en mayúsculas, sin tildes en la mayoría de casos). |
| `cod_mpio` | string (5 dígitos) | Código DIVIPOLA de municipio — join key hacia `municipios`. **Nunca convertir a int.** |
| `nombre_mpio` | string | Nombre del municipio tal como lo entrega la fuente. Para joins usa `cod_mpio`, no el nombre. |
| `cantidad` | int | Número de víctimas de hurto a personas en ese municipio ese día (siempre > 0). |

Clave primaria: `(fecha, cod_mpio)` — confirmada única en la fuente y
validada en cada build.

## Uso

```python
import polars as pl
from colombia_open import ColombiaOpen

hub = ColombiaOpen()
hurto = hub.load_polars("delincuencia_hurto_personas")

# Víctimas por año en Medellín
(
    hurto.filter(pl.col("cod_mpio") == "05001")
    .group_by("anio")
    .agg(pl.col("cantidad").sum())
    .sort("anio")
)

# Serie mensual nacional
hurto.group_by(pl.col("fecha").dt.truncate("1mo")).agg(pl.col("cantidad").sum())

# Tasa por 100 mil habitantes: join con demografia por (cod_mpio, anio)
poblacion = hub.load_polars("demografia").filter(pl.col("area_geografica") == "Total")
(
    hurto.group_by(["cod_mpio", "anio"])
    .agg(pl.col("cantidad").sum())
    .join(poblacion.select(["cod_mpio", "anio", "poblacion"]), on=["cod_mpio", "anio"])
    .with_columns((pl.col("cantidad") / pl.col("poblacion") * 100_000).alias("tasa_100k"))
)
```

`demografia` cubre 2018-2042, así que la tasa solo se puede calcular desde
2018.

## Limitaciones conocidas

- **2008 casi no tiene desagregación municipal.** Confirmado en vivo el
  2026-10-19: ese año la fuente trae una fila diaria con
  `cod_depto`/`cod_muni` = `"SIN ESTABLECER"` (365 filas, 64185 víctimas en
  total) y solo 76 municipios con código, contra ~630-1050 municipios en
  cualquier otro año. **Las filas "SIN ESTABLECER" se excluyen** del
  dataset — no tienen join posible con `municipios` y no se fabrica un
  código para ellas. El conteo excluido queda registrado en las `notes` de
  la metadata de staging de cada build, y el validador
  (`src/validation/_delincuencia.py`) reporta el año como **warning** de
  cobertura municipal baja (detectado dinámicamente contra la mediana de
  todos los años, no hardcodeado). Consecuencia práctica: **no compares
  2008 con otros años** — el total nacional de 2008 en este dataset
  subestima el real en ~64 mil víctimas.
- **La serie no es homogénea en el tiempo.** El número de municipios con
  registros crece de ~630 (2003) a ~1050 (2023), y el total de víctimas se
  multiplica por más de 10 en el mismo periodo. Parte de ese crecimiento
  refleja cambios en el registro y la denuncia (p. ej. la denuncia
  virtual), no solo en la criminalidad — no leas la tendencia de largo
  plazo como evolución del delito sin ese matiz.
- **El año en curso está incompleto**: la fuente se actualiza con corte
  mensual (último corte observado: 2026-08-31).
- **Discrepancia de `cod_mpio` con `municipios` (DIVIPOLA)** — igual que
  en `demografia` y `educacion_establecimientos`: son productos de
  entidades distintas (Policía vs. DANE). El validador reporta cualquier
  `cod_mpio` que no exista en el `municipios` vigente como warning, no
  como error.
- **Solo hurto a personas.** Los otros dos endpoints de delincuencia de la
  Policía en datos.gov.co (lesiones personales `72sg-cybi`, hurto por
  modalidades `6sqw-8cg5`) no están incluidos: usan un `codigo_dane` de 8
  dígitos y nombres de municipio con sufijos tipo "(CT)" que requieren su
  propia normalización — ver `docs/roadmap/roadmap.md`.
