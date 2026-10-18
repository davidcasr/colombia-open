# demografia

Proyecciones de población municipal de Colombia por área geográfica
(cabecera municipal / centros poblados y rural disperso / total), años
2018-2042.

- **Fuente**: DANE — "Proyecciones de Población y Estudios Demográficos
  (PPED)", hoja `PobMunicipalxÁrea`, descarga directa (no API):
  <https://www.dane.gov.co/files/censo2018/proyecciones-de-poblacion/Municipal/PPED-AreaMun-2018-2042_VP.xlsx>
- **Licencia**: `public-api-review-terms` — ver `docs/licenses/data_licenses.md`.
  El DANE no declara una licencia Creative Commons para este archivo (a
  diferencia de `divipola`, que sí la declara en datos.gov.co); sus
  términos de uso autorizan uso/transformación/análisis con atribución
  obligatoria. Se publica bajo la presunción de apertura de la Ley
  1712/2014 de Transparencia.
- **Extractor**: `src/extractors/demografia_extractor.py`.
- **Filas esperadas**: ~84225 (confirmado en vivo el 2026-10-18): 1123
  municipios × 25 años (2018-2042) × 3 categorías de área geográfica.

## Esquema

| Columna | Tipo | Descripción |
|---|---|---|
| `cod_dpto` | string (2 dígitos) | Código DIVIPOLA de departamento. **Nunca convertir a int.** |
| `nombre_dpto` | string | Nombre del departamento, como lo publica el DANE en este archivo. |
| `cod_mpio` | string (5 dígitos) | Código DIVIPOLA de municipio — join key hacia `municipios`. **Nunca convertir a int.** |
| `nombre_mpio` | string | Nombre del municipio. Los municipios que son "área no municipalizada" llevan el sufijo `(ANM)` tal como los publica el DANE. |
| `anio` | int | Año de la proyección, 2018 a 2042. No es un código administrativo — se mantiene como entero. |
| `area_geografica` | string | Una de: `"Cabecera Municipal"`, `"Centros Poblados y Rural Disperso"`, `"Total"`. `"Total"` es la suma de las otras dos — se conserva como fila propia porque así la publica el DANE, evitando que cada usuario tenga que sumarla. |
| `poblacion` | int | Población proyectada para esa combinación de municipio/año/área. |

La clave primaria es compuesta: `(cod_mpio, anio, area_geografica)`.

## Uso

```python
from colombia_open import ColombiaOpen

hub = ColombiaOpen()
demografia = hub.load_polars("demografia")

# Población total de Medellín en 2030
demografia.filter(
    (demografia["cod_mpio"] == "05001")
    & (demografia["anio"] == 2030)
    & (demografia["area_geografica"] == "Total")
)

hub.cross_view(["demografia", "municipios"], on="cod_mpio")
```

## Limitaciones conocidas

- **Discrepancia documentada entre dos productos del DANE.** Este dataset
  y `municipios` (DIVIPOLA, vía Socrata) son dos productos del DANE con
  ciclos de actualización distintos. Un código (`94663`, "Mapiripana
  (ANM)") aparece en `demografia` para toda la serie 2018-2042 pero ya no
  existe en el `municipios` vigente: desde el 1 de diciembre de 2019 esa
  área no municipalizada fue absorbida por el nuevo municipio de
  Barrancominas (`94343`), según la propia nota al pie del archivo DANE.
  El validador reporta esto como **warning**, no como error — ver
  `src/validation/_demografia.py`.
- **`area_geografica == "Total"` es redundante por diseño.** Se publica
  tal cual la entrega el DANE (no se deriva en el pipeline) para que el
  dato "total" nunca diverja de lo que el DANE certifica oficialmente.
- Sin desagregación por sexo o grupo de edad — este archivo es la versión
  municipal agregada por área geográfica, no el detalle demográfico
  completo que el DANE publica en otros archivos del mismo PPED.
