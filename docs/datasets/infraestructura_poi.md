# infraestructura_poi

Puntos de interés (POI) urbanos de interés cívico/público — salud,
educación, seguridad, finanzas, religión, gobierno, transporte y comercio
básico — geocodificados por municipio. Fuente: OpenStreetMap.

- **Fuente**: extracto de OpenStreetMap para Colombia, vía Geofabrik:
  <https://download.geofabrik.de/south-america/colombia-latest.osm.pbf>.
  Confirmado en vivo el 2026-10-20.
- **Licencia**: ODbL 1.0 — ver `docs/licenses/data_licenses.md`.
- **Extractor**: `src/extractors/infraestructura_poi_extractor.py`.
- **Filas esperadas**: ~58046 (58494 nodos clasificados en la fuente el
  2026-10-20, menos ~450 excluidos por no caer dentro de ningún polígono
  de `municipios_geometria` — ver Limitaciones).

## De dónde sale cada columna

OpenStreetMap es un grafo de ~48 millones de nodos (calles, bancas,
postes...) para Colombia. El extractor:

1. Filtra, a nivel C++ (`osmium.FileProcessor` + `KeyFilter`), solo los
   nodos que traen una etiqueta `amenity` o `shop`.
2. Clasifica cada uno contra una **lista curada** de valores (ver
   `_CATEGORIAS_AMENITY`/`_CATEGORIAS_SHOP` en el extractor) — el resto
   (bancas, parqueaderos, canecas de basura...) se descarta, no es un
   defecto de la fuente.
3. Geocodifica cada POI con un **join espacial punto-en-polígono** contra
   `municipios_geometria` (no contra el centroide más cercano de
   `municipios` — sería impreciso en municipios grandes o alargados).

## Esquema

| Columna | Tipo | Descripción |
|---|---|---|
| `osm_id` | int | ID del nodo en OpenStreetMap — clave primaria, única. Solo identifica nodos (puntos); ver Limitaciones. |
| `categoria` | string | Categoría cívica curada: `salud`, `educacion`, `seguridad`, `finanzas`, `religion`, `gobierno`, `transporte` o `comercio`. |
| `subcategoria` | string | Valor original de OpenStreetMap (`amenity` o `shop`), p. ej. "pharmacy", "school", "supermarket". |
| `nombre` | string | Etiqueta `name` del POI. Nulo si la fuente no la trae (~9% de los nodos) — no se rellena. |
| `cod_dpto` | string (2 dígitos) | Código DIVIPOLA de departamento, derivado del join espacial. **Nunca convertir a int.** |
| `cod_mpio` | string (5 dígitos) | Código DIVIPOLA de municipio, derivado del join espacial — join key hacia `municipios`. **Nunca convertir a int.** |
| `longitud` | float | Grados decimales, EPSG:4326. |
| `latitud` | float | Grados decimales, EPSG:4326. |

## Uso

```python
import polars as pl
from colombia_open import ColombiaOpen

hub = ColombiaOpen()
poi = hub.load_polars("infraestructura_poi")

# Farmacias por municipio
(
    poi.filter(pl.col("subcategoria") == "pharmacy")
    .group_by(["cod_mpio"])
    .agg(pl.len().alias("farmacias"))
    .sort("farmacias", descending=True)
)

# Acceso a salud por 100 mil habitantes: join con demografia
poblacion = hub.load_polars("demografia").filter(
    (pl.col("area_geografica") == "Total") & (pl.col("anio") == 2024)
)
(
    poi.filter(pl.col("categoria") == "salud")
    .group_by("cod_mpio")
    .agg(pl.len().alias("poi_salud"))
    .join(poblacion.select(["cod_mpio", "poblacion"]), on="cod_mpio")
    .with_columns((pl.col("poi_salud") / pl.col("poblacion") * 100_000).alias("poi_salud_100k"))
    .sort("poi_salud_100k", descending=True)
)

# Municipios sin ningún POI de seguridad mapeado (posible vacío de mapeo, no necesariamente de infraestructura real)
municipios = hub.load_polars("municipios")
con_seguridad = poi.filter(pl.col("categoria") == "seguridad")["cod_mpio"].unique()
municipios.filter(~pl.col("cod_mpio").is_in(con_seguridad))
```

## Limitaciones conocidas

- **Refleja qué tan mapeado está un lugar en OpenStreetMap, no
  necesariamente qué infraestructura existe de verdad.** Un municipio sin
  POI de una categoría puede no tenerla, o puede simplemente no estar
  mapeada todavía — OSM es de edición voluntaria y la cobertura es
  desigual entre zonas urbanas y rurales. No uses este dataset para
  concluir "ausencia" de un servicio sin cruzarlo con otra fuente.
- **Solo nodos (puntos), no polígonos de edificios.** Un supermercado o
  colegio puede estar mapeado como el contorno de su edificio (`way`) en
  vez de un punto — esos no se incluyen. Es la minoría de los casos para
  las categorías elegidas, pero existen.
- **Categorías curadas, no todo `amenity`/`shop` de OpenStreetMap.** Ver
  "De dónde sale cada columna" arriba — ampliar la lista es una decisión
  de alcance explícita, no algo que se infiera del dato.
- **~450 POI excluidos por geocodificación** (confirmado en vivo
  2026-10-20): caen fuera de cualquier polígono de `municipios_geometria`,
  casi todos en zonas de frontera o costeras — a veces por la
  simplificación de ese dataset (polígonos con tolerancia ~55m), a veces
  por limitaciones reales del extracto de OSM cerca de los límites del
  país.
- **Depende de `municipios_geometria` para existir** — si ese dataset
  tiene una discrepancia de cobertura (ver sus Limitaciones conocidas),
  se propaga aquí.
- **Snapshot de un momento dado**, no en tiempo real: el extracto de
  Geofabrik se regenera diariamente, pero el dataset publicado queda
  fijo a la fecha del build.
