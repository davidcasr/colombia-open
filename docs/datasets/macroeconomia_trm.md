# macroeconomia_trm

Tasa de Cambio Representativa del Mercado (TRM) — el promedio ponderado de
las operaciones de compra y venta de contado de dólares de Estados Unidos
a cambio de pesos colombianos. Serie diaria, 1991 a la fecha.

- **Fuente**: Superintendencia Financiera de Colombia (SUPERFINANCIERA) —
  "Tasa de Cambio Representativa del Mercado - TRM" (`32sa-8pi3`), vía la
  API Socrata de datos.gov.co: <https://www.datos.gov.co/resource/32sa-8pi3.json>.
  La TRM se calcula con la metodología del Banco de la República, pero el
  ente que la certifica y publica en datos.gov.co es la Superfinanciera —
  no el Banco directamente (corrección sobre `docs/roadmap/roadmap.md`,
  que la mapeaba bajo "Banco de la República").
- **Licencia**: CC BY-SA 4.0 (explícita en el portal) — ver
  `docs/licenses/data_licenses.md`.
- **Extractor**: `src/extractors/macroeconomia_trm_extractor.py`.
- **Filas esperadas**: ~8372 (confirmado en vivo el 2026-10-22),
  1991-12-02 a la fecha.

## La fuente más simple del catálogo

A diferencia de todo lo demás en `colombia-open`, esta fuente:

- **No tiene dimensión territorial** — es una serie nacional, no hay
  `cod_dpto`/`cod_mpio`, no hay join con `municipios`.
- **No necesita paginación** — 8372 filas caben en un solo request.
- **No necesita agregación** — se publica tal cual la entrega la fuente.

## Granularidad

La fuente no es "un valor por día calendario", es "un valor por
publicación": cada fila trae un rango de vigencia
(`vigenciadesde`/`vigenciahasta`) que puede cubrir varios días — por
ejemplo, la TRM certificada un viernes suele aplicar también el fin de
semana. Confirmado en vivo: 1942 de 8372 filas tienen un rango de más de
un día. Se publica **una fila por publicación**, con `vigente_hasta` para
que quien necesite expandir a un valor por día calendario lo haga por su
cuenta — no se fabrican filas para los días sin publicación propia.

## Esquema

| Columna | Tipo | Descripción |
|---|---|---|
| `fecha` | date | Inicio de la vigencia (`vigenciadesde` en la fuente) — clave primaria, única. |
| `vigente_hasta` | date | Fin de la vigencia (`vigenciahasta`). Igual a `fecha` la mayoría de las veces; mayor cuando la vigencia cubre varios días (fines de semana/festivos). |
| `trm` | float | Pesos colombianos (COP) por dólar estadounidense (USD). Siempre > 0. |

## Uso

```python
import polars as pl
from colombia_open import ColombiaOpen

hub = ColombiaOpen()
trm = hub.load_polars("macroeconomia_trm")

# TRM más reciente
trm.sort("fecha", descending=True).head(1)

# Promedio mensual
(
    trm.with_columns(pl.col("fecha").dt.strftime("%Y-%m").alias("mes"))
    .group_by("mes")
    .agg(pl.col("trm").mean().round(2).alias("trm_promedio"))
    .sort("mes")
)

# Expandir a un valor por día calendario (si lo necesitas día a día,
# incluidos los que la fuente no publicó por separado)
trm.select(
    pl.date_ranges("fecha", "vigente_hasta").alias("dia"), "trm"
).explode("dia")
```

## Limitaciones conocidas

- **No es una serie de "un valor por día calendario" por defecto** — ver
  Granularidad arriba. Si necesitas rellenar los días entre `fecha` y
  `vigente_hasta`, hazlo tú (ver ejemplo de uso); no se fabrica en el
  pipeline.
- **Serie nacional, sin desagregación territorial.** No tiene `cod_mpio`
  ni `cod_dpto` — no aplica el criterio de integridad referencial contra
  `municipios` que sí tienen los demás datasets del catálogo.
- **El día en curso puede no estar publicado todavía** — la Superfinanciera
  certifica la TRM con un día de rezago en algunos casos; si cargas el
  dataset muy temprano en el día, el valor de "hoy" puede todavía no
  existir en la fuente.
