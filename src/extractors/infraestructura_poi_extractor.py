"""Extractor de puntos de interés (POI) urbanos, fuente OpenStreetMap.

Fuente primaria: extracto de OpenStreetMap para Colombia vía Geofabrik
(`download.geofabrik.de/south-america/colombia-latest.osm.pbf`), licencia
ODbL 1.0. Confirmado en vivo el 2026-10-20: ~332MB, actualizado el mismo
día. Dominio nuevo, mapeado por primera vez el 2026-10-17 (ver
docs/roadmap/roadmap.md).

A diferencia de las demás fuentes (todas Socrata/Excel), este extracto es
un `.osm.pbf` — el grafo completo de OpenStreetMap para el país (~48
millones de nodos: calles, bancas, postes, edificios...). Se usa
`pyosmium` con un filtro a nivel C++ (`osmium.FileProcessor` +
`osmium.filter.KeyFilter`) para quedarse solo con los nodos que traen
`amenity` o `shop` — sin este filtro, iterar los 48M nodos en Python toma
~25 minutos; con él, ~5 segundos.

Decisiones de alcance:

- **Solo nodos (puntos), no ways (polígonos).** Un supermercado puede estar
  mapeado como nodo o como contorno de edificio (way); aquí solo se
  publican los nodos. Es la gran mayoría de los POI de las categorías
  elegidas y evita el costo de resolver geometría de ways (requiere
  cachear ubicación de cada nodo referenciado — mucho más pesado).
- **Categorías curadas, no todo `amenity`/`shop`.** OpenStreetMap tiene
  cientos de valores de `amenity`/`shop` (bancas, canecas de basura,
  parqueaderos...). Se publica un subconjunto de interés cívico/público:
  salud, educación, seguridad, finanzas, religión, gobierno, transporte
  (combustible/terminal) y comercio básico (supermercado, tienda de
  barrio, centro comercial) — ver `_CATEGORIAS_AMENITY`/`_CATEGORIAS_SHOP`.
  Ampliar la lista es un cambio de alcance documentado, no un bug.
- **Geocodificación por polígono, no por centroide más cercano.** Cada POI
  se ubica dentro de un municipio con un join espacial punto-en-polígono
  contra `municipios_geometria` (no contra el centroide de `municipios` —
  sería impreciso en municipios grandes o alargados). Confirmado en vivo:
  99.2% de los POI caen dentro de algún polígono; el resto (zonas de
  frontera/costeras donde la simplificación del polígono los deja justo
  afuera) se excluye — ver notas de staging.

Se invoca siempre como módulo, nunca como script suelto:
`python -m src.extractors.infraestructura_poi_extractor` desde la raíz del
repo. Ver `.claude/rules/extractors.md` §6. A diferencia de los demás
extractores, este **requiere** el DataFrame de `municipios_geometria` para
geocodificar — `fetch()` lo recibe vía kwarg (`municipios_geometria=...`);
invocado como script suelto, lo obtiene corriendo
`MunicipiosGeometriaExtractor` él mismo (ver `if __name__ == "__main__":`).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import geopandas as gpd
import osmium
import osmium.filter
import polars as pl
import shapely.wkt
from requests import RequestException
from shapely.geometry import Point

from src.extractors.base import (
    RAW_DIR,
    ROOT_DIR,
    STAGING_DIR,
    BaseExtractor,
    ExtractionResult,
    ReusePolicy,
    compute_sha256,
    ensure_staging_directories,
    write_raw_snapshot_atomic,
    write_staging_csv_atomic,
)
from src.extractors.http_utils import get_bytes

DATASET_NAME = "infraestructura_poi"
SOURCE_URL = "https://download.geofabrik.de/south-america/colombia-latest.osm.pbf"
SOURCE_NAME = "OpenStreetMap contributors, vía Geofabrik — extracto Colombia"

PBF_DOWNLOAD_TIMEOUT_SECONDS = 300
EXPECTED_MIN_ROWS = 50_000

REUSE_POLICY = ReusePolicy(
    status="open-attribution",
    license="ODbL 1.0",
    license_url="https://opendatacommons.org/licenses/odbl/1-0/",
    attribution_required=True,
    redistribution_ok=True,
    summary=(
        "Datos de OpenStreetMap, licencia ODbL 1.0 (Open Database License): "
        "redistribuir con atribución '© OpenStreetMap contributors' y, por "
        "ser un extracto sustancial de la base de datos (no un 'produced "
        "work' puntual), bajo la misma licencia ODbL — ver "
        "docs/licenses/data_licenses.md."
    ),
)

# Qué cae a fallback: problemas de la FUENTE (red caída, HTTP 4xx/5xx tras
# reintentos, .pbf corrupto o con formato inesperado — pyosmium lanza
# RuntimeError genérico para ambos). Un bug de programación real debe
# reventar. Ver `.claude/rules/extractors.md` §1.
EXPECTED_FETCH_FAILURES: tuple[type[Exception], ...] = (
    RequestException,
    RuntimeError,
    OSError,
    KeyError,
    ValueError,
    TypeError,
)

# amenity/shop -> categoría cívica curada. Ver docstring del módulo.
_CATEGORIAS_AMENITY: dict[str, str] = {
    "hospital": "salud",
    "clinic": "salud",
    "doctors": "salud",
    "pharmacy": "salud",
    "dentist": "salud",
    "veterinary": "salud",
    "school": "educacion",
    "college": "educacion",
    "university": "educacion",
    "kindergarten": "educacion",
    "language_school": "educacion",
    "police": "seguridad",
    "fire_station": "seguridad",
    "bank": "finanzas",
    "atm": "finanzas",
    "place_of_worship": "religion",
    "townhall": "gobierno",
    "post_office": "gobierno",
    "community_centre": "gobierno",
    "courthouse": "gobierno",
    "embassy": "gobierno",
    "fuel": "transporte",
    "bus_station": "transporte",
    "marketplace": "comercio",
}
_CATEGORIAS_SHOP: dict[str, str] = {
    "supermarket": "comercio",
    "convenience": "comercio",
    "mall": "comercio",
    "department_store": "comercio",
}

# Fallback mínimo para desarrollo offline / CI sin red. NUNCA se publica.
# POI reales observados en la fuente (2026-10-20) — SIN cod_dpto/cod_mpio:
# el join espacial contra `_FALLBACK_MUNICIPIOS_GEOMETRIA` los asigna igual
# que en vivo, para que el fallback ejercite el mismo camino de código.
INFRAESTRUCTURA_POI_FALLBACK_DATA: list[dict[str, Any]] = [
    {
        "osm_id": 313416844,
        "categoria": "salud",
        "subcategoria": "hospital",
        "nombre": "Clínica El Bosque",
        "lon": -74.030771,
        "lat": 4.711816,
    },
    {
        "osm_id": 292776528,
        "categoria": "finanzas",
        "subcategoria": "bank",
        "nombre": "Davivienda",
        "lon": -74.137405,
        "lat": 4.63605,
    },
    {
        "osm_id": 265686842,
        "categoria": "comercio",
        "subcategoria": "supermarket",
        "nombre": "Carulla",
        "lon": -74.060183,
        "lat": 4.726381,
    },
    {
        "osm_id": 339430113,
        "categoria": "educacion",
        "subcategoria": "school",
        "nombre": "Santa Clara de Asissi",
        "lon": -75.604613,
        "lat": 6.242521,
    },
    {
        "osm_id": 1469634100,
        "categoria": "seguridad",
        "subcategoria": "police",
        "nombre": "Santa Elena",
        "lon": -75.49974,
        "lat": 6.211265,
    },
    {
        "osm_id": 369123982,
        "categoria": "religion",
        "subcategoria": "place_of_worship",
        "nombre": "Capilla Hospital Universitario",
        "lon": -75.564413,
        "lat": 6.262663,
    },
    {
        "osm_id": 999999999,
        "categoria": "comercio",
        "subcategoria": "supermarket",
        "nombre": "Fuera de cualquier municipio (prueba de exclusión)",
        "lon": 0.0,
        "lat": 0.0,
    },
]

# Polígonos simplificados reales (mismos que
# `municipios_geometria_extractor.MUNICIPIOS_GEOMETRIA_FALLBACK_DATA`,
# duplicados aquí para que este extractor no dependa de otro módulo para su
# propio fallback) — Bogotá y Medellín, suficientes para geocodificar la
# muestra de arriba.
_FALLBACK_MUNICIPIOS_GEOMETRIA_WKT: dict[str, tuple[str, str]] = {
    "11001": (
        "11",
        "POLYGON ((-74.0742 4.8365, -74.0056 4.8214, -74.0016 4.6753, "
        "-74.0314 4.6461, -73.9861 4.6291, -74.0053 4.5606, -74.0726 4.5131, "
        "-74.1121 4.4331, -74.0982 4.3456, -74.1527 4.2546, -74.11 4.1819, "
        "-74.1269 4.0485, -74.1507 4.0048, -74.2174 4.0109, -74.3168 3.8813, "
        "-74.2966 3.8189, -74.3356 3.8217, -74.4396 3.7306, -74.3596 3.9137, "
        "-74.3746 3.9859, -74.3299 4.1305, -74.2456 4.1032, -74.218 4.3608, "
        "-74.1736 4.5409, -74.2226 4.6294, -74.1585 4.6628, -74.177 4.7029, "
        "-74.1261 4.7294, -74.0742 4.8365))",
    ),
    "05001": (
        "05",
        "POLYGON ((-75.6697 6.3736, -75.6344 6.3173, -75.4992 6.2953, "
        "-75.4847 6.1909, -75.5324 6.1979, -75.5398 6.1703, -75.6131 6.1988, "
        "-75.68 6.1641, -75.7193 6.3415, -75.714 6.3714, -75.6697 6.3736))",
    ),
}


def _fallback_municipios_geometria() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "cod_dpto": [v[0] for v in _FALLBACK_MUNICIPIOS_GEOMETRIA_WKT.values()],
            "cod_mpio": list(_FALLBACK_MUNICIPIOS_GEOMETRIA_WKT.keys()),
            "geometry_wkt": [v[1] for v in _FALLBACK_MUNICIPIOS_GEOMETRIA_WKT.values()],
        }
    )


_OUTPUT_COLUMNS = [
    "osm_id",
    "categoria",
    "subcategoria",
    "nombre",
    "cod_dpto",
    "cod_mpio",
    "longitud",
    "latitud",
]

_SCHEMA = {
    "osm_id": pl.Int64,
    "categoria": pl.Utf8,
    "subcategoria": pl.Utf8,
    "nombre": pl.Utf8,
    "cod_dpto": pl.Utf8,
    "cod_mpio": pl.Utf8,
    "longitud": pl.Float64,
    "latitud": pl.Float64,
}


def _classify(amenity: str | None, shop: str | None) -> tuple[str, str] | None:
    """Devuelve (categoria, subcategoria) si el POI cae en la lista curada,
    o None si no — los demás valores de amenity/shop se descartan en la
    fuente, no se cuentan como "excluidos" (no es un defecto, es alcance)."""
    if amenity is not None and amenity in _CATEGORIAS_AMENITY:
        return _CATEGORIAS_AMENITY[amenity], amenity
    if shop is not None and shop in _CATEGORIAS_SHOP:
        return _CATEGORIAS_SHOP[shop], shop
    return None


def _extract_poi_nodes(pbf_path: str) -> list[dict[str, Any]]:
    """Lee el .pbf y devuelve los nodos de la lista curada ya clasificados
    (categoria, subcategoria), sin geocodificar todavía. Filtra a nivel
    C++ con `KeyFilter('amenity', 'shop')` — sin esto, iterar los ~48M
    nodos del archivo en Python es ~300x más lento (ver docstring)."""
    rows: list[dict[str, Any]] = []
    processor = osmium.FileProcessor(pbf_path, osmium.osm.NODE).with_filter(
        osmium.filter.KeyFilter("amenity", "shop")
    )
    for node in processor:
        if not isinstance(node, osmium.osm.Node):
            continue  # inalcanzable en la práctica: el FileProcessor ya filtra por NODE
        tags = node.tags
        classified = _classify(tags.get("amenity"), tags.get("shop"))
        if classified is None:
            continue
        if not node.location.valid():
            continue
        categoria, subcategoria = classified
        rows.append(
            {
                "osm_id": node.id,
                "categoria": categoria,
                "subcategoria": subcategoria,
                "nombre": tags.get("name"),
                "lon": node.location.lon,
                "lat": node.location.lat,
            }
        )
    return rows


def _municipios_geodataframe(municipios_geometria: pl.DataFrame) -> gpd.GeoDataFrame:
    pdf = municipios_geometria.select(["cod_dpto", "cod_mpio", "geometry_wkt"]).to_pandas()
    geometry = pdf["geometry_wkt"].map(shapely.wkt.loads)
    return gpd.GeoDataFrame(pdf[["cod_dpto", "cod_mpio"]], geometry=geometry, crs="EPSG:4326")


def _normalize(
    poi_rows: list[dict[str, Any]], municipios_geometria: pl.DataFrame
) -> tuple[pl.DataFrame, int, int]:
    """Geocodifica `poi_rows` (osm_id/categoria/subcategoria/nombre/lon/lat)
    contra los polígonos de `municipios_geometria` (join espacial
    punto-en-polígono). Devuelve (df, sin_municipio, duplicados_borde)."""
    if not poi_rows:
        return pl.DataFrame(schema=_SCHEMA), 0, 0

    points = gpd.GeoDataFrame(
        poi_rows,
        geometry=[Point(r["lon"], r["lat"]) for r in poi_rows],
        crs="EPSG:4326",
    )
    mpios = _municipios_geodataframe(municipios_geometria)

    joined = gpd.sjoin(points, mpios, how="left", predicate="within")
    # La simplificación de municipios_geometria puede crear micro-solapes en
    # frontera: un POI justo en el límite puede caer "dentro" de 2 polígonos
    # a la vez. Nos quedamos con la primera coincidencia, determinista por
    # orden de `municipios_geometria` (ya viene ordenado por cod_mpio).
    before = len(joined)
    joined = joined[~joined.index.duplicated(keep="first")]
    border_duplicates = before - len(joined)

    sin_municipio = int(joined["cod_mpio"].isna().sum())
    matched = joined[joined["cod_mpio"].notna()].copy()

    df = pl.DataFrame(
        {
            "osm_id": matched["osm_id"].astype("int64").tolist(),
            "categoria": matched["categoria"].tolist(),
            "subcategoria": matched["subcategoria"].tolist(),
            "nombre": matched["nombre"].tolist(),
            "cod_dpto": matched["cod_dpto"].tolist(),
            "cod_mpio": matched["cod_mpio"].tolist(),
            "longitud": matched.geometry.x.tolist(),
            "latitud": matched.geometry.y.tolist(),
        },
        schema=_SCHEMA,
    ).select(_OUTPUT_COLUMNS)

    return df.sort("osm_id"), sin_municipio, border_duplicates


def _normalization_notes(sin_municipio: int, border_duplicates: int) -> list[str]:
    notes: list[str] = []
    if sin_municipio > 0:
        notes.append(
            f"{sin_municipio} POI excluidos por no caer dentro de ningún polígono de "
            "municipios_geometria (zonas de frontera/costeras, o el efecto de la "
            "simplificación de ese dataset); ver docs/datasets/infraestructura_poi.md."
        )
    if border_duplicates > 0:
        notes.append(
            f"{border_duplicates} POI en el límite entre dos municipios (polígonos "
            "simplificados con micro-solape) — se asignó el primero por orden de cod_mpio."
        )
    return notes


class InfraestructuraPoiExtractor(BaseExtractor):
    @property
    def dataset_name(self) -> str:
        return DATASET_NAME

    def fetch(
        self, *, municipios_geometria: pl.DataFrame | None = None, **kwargs: Any
    ) -> ExtractionResult:
        del kwargs
        if municipios_geometria is None:
            raise ValueError(
                "InfraestructuraPoiExtractor.fetch() requiere municipios_geometria "
                "(el DataFrame de municipios_geometria_extractor) para geocodificar "
                "cada POI — ver docstring del módulo."
            )
        try:
            pbf_bytes = get_bytes(SOURCE_URL, timeout=PBF_DOWNLOAD_TIMEOUT_SECONDS)

            ensure_staging_directories()
            timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
            raw_path = RAW_DIR / f"infraestructura_poi_{timestamp}.osm.pbf"
            write_raw_snapshot_atomic(raw_path, pbf_bytes)

            poi_rows = _extract_poi_nodes(str(raw_path))
            df, sin_municipio, border_duplicates = _normalize(poi_rows, municipios_geometria)
            notes = _normalization_notes(sin_municipio, border_duplicates)
            if df.height < EXPECTED_MIN_ROWS:
                notes.append(
                    f"La fuente devolvió solo {df.height} filas, menos de las "
                    f"{EXPECTED_MIN_ROWS} esperadas como mínimo."
                )

            return ExtractionResult(
                dataset=DATASET_NAME,
                dataframe=df,
                source_name=SOURCE_NAME,
                source_url=SOURCE_URL,
                source_mode="live",
                source_detail=(
                    "Extracto .osm.pbf de Geofabrik; nodos con amenity/shop en la lista "
                    "curada, geocodificados por join espacial contra municipios_geometria"
                ),
                reuse_policy=REUSE_POLICY,
                raw_snapshot_path=str(raw_path.relative_to(ROOT_DIR)),
                snapshot_hash=compute_sha256(pbf_bytes),
                notes=notes,
            )
        except EXPECTED_FETCH_FAILURES as exc:
            df, sin_municipio, border_duplicates = _normalize(
                INFRAESTRUCTURA_POI_FALLBACK_DATA, municipios_geometria
            )
            return ExtractionResult(
                dataset=DATASET_NAME,
                dataframe=df,
                source_name=SOURCE_NAME,
                source_url=SOURCE_URL,
                source_mode="fallback",
                source_detail=f"fallback embebido tras fallo de fetch en vivo: {exc!r}",
                reuse_policy=REUSE_POLICY,
                notes=[
                    "source_mode=fallback: dataset de muestra para desarrollo offline, "
                    "NO se publica.",
                    *_normalization_notes(sin_municipio, border_duplicates),
                ],
            )

    def write_staging(self, result: ExtractionResult) -> Path:
        ensure_staging_directories()
        csv_path = STAGING_DIR / "infraestructura_poi.csv"
        metadata_path = STAGING_DIR / "infraestructura_poi.metadata.json"
        return write_staging_csv_atomic(
            result.dataframe, csv_path, metadata_path, result.to_staging_metadata()
        )


if __name__ == "__main__":
    from src.extractors.municipios_geometria_extractor import MunicipiosGeometriaExtractor

    geometria = MunicipiosGeometriaExtractor().run(dry_run=True).dataframe
    extractor = InfraestructuraPoiExtractor()
    outcome = extractor.run(municipios_geometria=geometria)
    print(f"[{DATASET_NAME}] source_mode={outcome.source_mode} rows={outcome.dataframe.height}")
