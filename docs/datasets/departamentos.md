# departamentos

Departamentos de Colombia: código DIVIPOLA y nombre oficial.

- **Fuente**: DANE — "DIVIPOLA- Códigos municipios" (`gdxc-w37w`), vía la
  API Socrata de datos.gov.co: <https://www.datos.gov.co/resource/gdxc-w37w.json>
- **Licencia**: CC BY-SA 4.0 — ver `docs/licenses/data_licenses.md`.
- **Extractor**: `src/extractors/divipola_extractor.py` (produce la tabla
  cruda; `src/builders/datasets.py::derive_departamentos` deriva esta tabla
  única por `cod_dpto`).
- **Filas esperadas**: 33.

## Esquema

| Columna | Tipo | Descripción |
|---|---|---|
| `cod_dpto` | string (2 dígitos) | Código DIVIPOLA de departamento. **Nunca convertir a int** — pierde el cero inicial. |
| `nombre_dpto` | string | Nombre oficial, como lo publica el DANE (mayúsculas, con tildes). |
| `nombre_dpto_clean` | string | `nombre_dpto` normalizado: minúsculas, sin tildes, sin puntuación — para joins/búsqueda determinística. |

## Uso

```python
from colombia_open import ColombiaOpen

hub = ColombiaOpen()
departamentos = hub.load_polars("departamentos")
```

```sql
-- DuckDB
SELECT * FROM 'data/normalized/departamentos.parquet' LIMIT 10;
```

## Limitaciones conocidas

- Nombres compuestos (ej. "ARCHIPIÉLAGO DE SAN ANDRÉS, PROVIDENCIA Y SANTA
  CATALINA") producen un `nombre_dpto_clean` largo con guiones bajos — la
  búsqueda por nombre en `ColombiaOpen.resolve_municipios`-equivalente es
  **exacta tras normalizar**, no fuzzy. Buscar por `cod_dpto` es siempre
  más confiable.
