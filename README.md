# 🇨🇴 Colombia Open

Datasets públicos de Colombia, **curados, normalizados y validados**, para
que cualquiera los use desde Python sin lidiar con los portales, APIs y
Excels inconsistentes de cada institución oficial.

```python
from colombia_open import ColombiaOpen

hub = ColombiaOpen()
municipios = hub.load_polars("municipios")
departamentos = hub.load_polars("departamentos")
```

> **Proyecto en MVP activo.** Dos fuentes están implementadas (DIVIPOLA:
> departamentos + municipios; y demografía: proyecciones de población
> municipal, ambas DANE). Primer [GitHub Release](https://github.com/davidcasr/colombia-open/releases)
> publicado y landing page en vivo en
> [davidcasr.com/colombia-open](https://davidcasr.com/colombia-open/). No
> publicado en PyPI todavía — ver
> [Estado del proyecto](#estado-del-proyecto).

## Por qué existe

Los datos públicos de Colombia existen, son abiertos, y están dispersos en
decenas de portales con formatos, convenciones de código y calidad de API
distintas (DANE, IDEAM, ICFES, DNP, Banco de la República, XM...). El trabajo
real casi nunca es "¿existe el dato?" sino "¿cuánto tiempo me toma
normalizarlo, validarlo, y confiar en que no tiene errores silenciosos
(ej. un código de municipio que perdió el cero inicial en Excel)?"

`colombia-open` hace ese trabajo una vez, por fuente, y lo distribuye como
tablas [Polars](https://pola.rs)/Parquet listas para usar — con su fuente
oficial, licencia y fecha de actualización siempre visibles.

## Instalación

```bash
pip install colombia-open  # próximamente — ver "Estado del proyecto"
```

Para correr el pipeline localmente (extraer datos en vivo, no solo leerlos):

```bash
git clone https://github.com/davidcasr/colombia-open.git
cd colombia-open
make bootstrap   # crea .venv e instala con extras pipeline+dev
make build       # extract -> normalize -> validate -> data/normalized/
make test
```

## Uso

```python
from colombia_open import ColombiaOpen

hub = ColombiaOpen()

hub.list_datasets()
# ["departamentos", "municipios", "demografia"]

municipios = hub.load_polars("municipios")
municipios.filter(municipios["cod_dpto"] == "05")  # municipios de Antioquia

hub.resolve_municipios(["Medellín", "cali", "BOGOTA"])
# resuelve nombres a código DIVIPOLA, sin fuzzy matching (coincidencia exacta
# normalizada: sin tildes, minúsculas)

hub.cross_view(["municipios", "departamentos"], on="cod_dpto")
# join listo entre dos datasets que comparten una clave territorial

hub.provenance("municipios")
# {"source_name": "DANE — DIVIPOLA...", "source_url": "...", "source_mode": "live", ...}
```

CLI equivalente:

```bash
colombia-open list
colombia-open show municipios
colombia-open path municipios --output parquet
colombia-open example municipios --kind python
colombia-open validate municipios
```

## Datasets disponibles

| Dataset         | Descripción                                                                      | Fuente                 | Filas | Licencia     |
| --------------- | -------------------------------------------------------------------------------- | ---------------------- | ----- | ------------ |
| `departamentos` | Departamentos: código DIVIPOLA (2 dígitos) + nombre                              | DANE, vía datos.gov.co | 33    | CC BY-SA 4.0 |
| `municipios`    | Municipios: código DIVIPOLA (5 dígitos), nombre, departamento, centroide lon/lat | DANE, vía datos.gov.co | ~1122 | CC BY-SA 4.0 |
| `demografia`    | Proyecciones de población municipal por área geográfica, 2018-2042              | DANE (descarga directa) | ~84225 | Términos DANE (público) |

Ver `docs/roadmap/roadmap.md` para las ~14 fuentes mapeadas (implementadas y
pendientes) y `docs/licenses/data_licenses.md` para el detalle legal de cada una.

## Instalación con extras

| Extra        | Para qué                                                  | Incluye                                       |
| ------------ | --------------------------------------------------------- | --------------------------------------------- |
| (base)       | Solo **leer** datos ya publicados                         | polars, pyarrow, requests, platformdirs       |
| `pipeline`   | Correr extract→build→validate localmente                  | duckdb, pandas, openpyxl, tenacity, structlog |
| `scraping`   | Fuentes sin API/descarga directa (entorno aparte)         | curl_cffi, beautifulsoup4, defusedxml         |
| `geo`        | Lookups geoespaciales (polígonos, cuando existan)         | geopandas, shapely                            |
| `validation` | Validación estricta de esquema (Frictionless)             | frictionless                                  |
| `mcp`        | Servidor MCP para que agentes de IA consulten el catálogo | mcp                                           |

```bash
pip install "colombia-open[pipeline]"
```

## Filosofía: una fuente por fin de semana

Este proyecto **no** se construye de golpe. Cada fuente nueva se implementa
de punta a punta (extractor + builder + validación + registro + tests +
docs) antes de empezar la siguiente. El resto de las fuentes candidatas
quedan mapeadas en `docs/roadmap/roadmap.md` con su dificultad de acceso, sin
implementar, hasta que les toque su turno.

La razón de ingeniería: la prioridad #1 no es "cuántas fuentes tenemos" sino
"qué tan fácil es agregar la fuente número N+1 sin releer todo el código
cada vez" — por eso existe la skill `.claude/skills/new-source/` y el
comando `/next-source`. Ver `CLAUDE.md` para el detalle completo.

## Arquitectura

```
src/
├── colombia_open/     # librería pública (pip install), deps livianas
├── extractors/        # uno por fuente institucional — fetch + fallback + raw snapshot
├── builders/          # staging -> normalizado (parquet/json) + catálogo
├── validation/        # reglas por dominio, funciones puras
└── registry/          # qué datasets existen, su esquema y su licencia

data/
├── raw/           # snapshots crudos, write-once (no se edita después)
├── staging/       # CSV normalizado + metadata.json por extractor
├── normalized/    # parquet/json finales + dataset_catalog.json (lo que lee la librería)
└── registry/      # datasets.json — fuente de verdad estática del registro
```

La librería pública (`colombia_open/`) nunca importa código de pipeline
(`extractors/`, `builders/`, `validation/`) — así `pip install colombia-open`
se mantiene liviano. El primer uso descarga y cachea el bundle de datos
publicado en GitHub Releases (con verificación SHA256); en desarrollo, lee
directamente `data/normalized/` si ya corriste `make build`.

## Estado del proyecto

- ✅ Patrón extractor/builder/validación/registro probado con dos fuentes
  (DIVIPOLA y demografía) de dominios distintos (API Socrata y descarga
  directa de Excel).
- ✅ [GitHub Releases](https://github.com/davidcasr/colombia-open/releases)
  publicados (último: `v0.2.0`, bundle de datos con SHA256, incluye las
  tres fuentes) — `ColombiaOpen()` ya puede descargarlo y cachearlo
  automáticamente sin tener que correr el pipeline localmente (ver
  `data_manager.py`). Convención de versionado: `.claude/rules/releases.md`.
- ⬜ Todavía no se publica en PyPI — por ahora la instalación es vía
  `git clone` + `make bootstrap`, o consumiendo el bundle del Release.
- ✅ Landing page (`site/`, ver `docs/brand/design-system.md`) deployada en
  [davidcasr.com/colombia-open](https://davidcasr.com/colombia-open/).
- Ver `docs/roadmap/roadmap.md` para qué sigue.

## Legal

El código es MIT (`LICENSE`). Cada dataset conserva la licencia de su fuente
original — ver `docs/licenses/data_licenses.md` antes de redistribuir cualquier dataset
fuera de este paquete.

## Contribuir

Hecho por [David Castro](https://github.com/davidcasr). El flujo de trabajo
está pensado para sesiones de Claude Code recurrentes — ver `CLAUDE.md` si
vas a contribuir con un agente de IA.
