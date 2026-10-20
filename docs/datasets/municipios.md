# municipios

Municipios de Colombia: código DIVIPOLA, nombre, departamento y centroide.

- **Fuente**: DANE — "DIVIPOLA- Códigos municipios" (`gdxc-w37w`), vía la
  API Socrata de datos.gov.co: <https://www.datos.gov.co/resource/gdxc-w37w.json>
- **Licencia**: CC BY-SA 4.0 — ver `docs/licenses/data_licenses.md`.
- **Extractor**: `src/extractors/divipola_extractor.py`.
- **Filas esperadas**: ~1122 (confirmado en vivo el 2026-10-17).

## Esquema

| Columna | Tipo | Descripción |
|---|---|---|
| `cod_dpto` | string (2 dígitos) | Código DIVIPOLA de departamento — join key hacia `departamentos`. |
| `nombre_dpto` | string | Nombre del departamento, denormalizado para evitar un join obligatorio. |
| `cod_mpio` | string (5 dígitos) | Código DIVIPOLA de municipio. **Nunca convertir a int.** |
| `nombre_mpio` | string | Nombre oficial del municipio, como lo publica el DANE. **Puede diferir del nombre coloquial** (ej. Cali es "SANTIAGO DE CALI" en DIVIPOLA). |
| `nombre_mpio_clean` | string | `nombre_mpio` normalizado (minúsculas, sin tildes) — usado por `hub.resolve_municipios()`. |
| `tipo_municipio` | string | "Municipio", "Capital", u otra categoría según la fuente. |
| `longitud` | float | Centroide, grados decimales. Puede ser nulo. |
| `latitud` | float | Centroide, grados decimales. Puede ser nulo. |

## Uso

```python
from colombia_open import ColombiaOpen

hub = ColombiaOpen()
municipios = hub.load_polars("municipios")
municipios.filter(municipios["cod_dpto"] == "05")  # municipios de Antioquia

hub.resolve_municipios(["Medellín", "Santiago de Cali"])
hub.cross_view(["municipios", "departamentos"], on="cod_dpto")
```

## Limitaciones conocidas

- **Sin geometría de polígonos.** Este dataset tiene código + nombre +
  centroide, NO los polígonos del Marco Geoestadístico Nacional (MGN) —
  esos viven en el dataset separado `municipios_geometria` (join por
  `cod_mpio`), para no cargarle a quien solo necesita nombre/centroide con
  el peso de los polígonos.
- `resolve_municipios()` hace coincidencia **exacta tras normalizar**
  (sin tildes, minúsculas), no fuzzy matching — "Cali" no resuelve porque
  el nombre oficial DIVIPOLA es "SANTIAGO DE CALI". Usa el nombre oficial
  o el código directamente si lo conoces.
