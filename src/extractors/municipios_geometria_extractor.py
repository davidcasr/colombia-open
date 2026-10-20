"""Extractor de geometría de polígonos municipales (MGN), vía mirror HDX.

Segunda iteración de `divipola` (ver docs/roadmap/roadmap.md, sección "Por
qué geografía fue primero"): agrega los polígonos del Marco Geoestadístico
Nacional (DANE) que `divipola`/`municipios` no incluye (solo centroide).

Fuente primaria: Humanitarian Data Exchange (HDX), dataset "Colombia -
Subnational Administrative Boundaries" (`cod-ab-col`, id
`50ea7fee-f9af-45a7-8a52-abb9c790a0b6`), publicado por OCHA (ROLAC/FISS) a
partir del Marco Geoestadístico Nacional del DANE. Licencia CC BY-IGO 3.0.
Confirmado en vivo el 2026-10-20: recurso "COL Administrative Divisions
Shapefiles.zip" (~117MB), nivel ADM2 (municipio) = 1122 filas, 2020-04-16.

https://data.humdata.org/dataset/cod-ab-col

El zip trae 4 niveles administrativos (admin0-3) como shapefiles
independientes; se usa solo el nivel ADM2 (municipio) — el shapefile se
localiza dentro del zip por patrón (`*admbnda_adm2*.shp` + sus componentes
`.dbf`/`.shx`/`.prj`/`.cpg`), no por nombre exacto, porque HDX versiona el
nombre de archivo con la fecha de la vigencia (hoy `20200416`) y puede
cambiar en una actualización futura del recurso.

Decisiones de alcance:

- **Geometría simplificada, no survey-grade.** El polígono original tiene
  ~5.7 millones de vértices en total (perfecto para GIS, pesado para una
  librería de propósito general). Se simplifica con tolerancia de 0.0005°
  (~55m en el ecuador, Douglas-Peucker con `preserve_topology=True`) y se
  redondean las coordenadas a 6 decimales (~11cm) antes de serializar a
  WKT — reduce el tamaño del dataset en >90% manteniendo la forma
  reconocible de cada municipio. No usar este dataset para análisis que
  requiera precisión catastral.
- **`area_km2` se calcula sobre la geometría ORIGINAL** (antes de
  simplificar), con área geodésica (`pyproj.Geod(ellps="WGS84")`), para que
  no cargue el error de la simplificación.
- **No se publica `nombre_mpio` aquí.** El nombre vive en `municipios`
  (mismo `cod_mpio`, join directo) — evita mantener dos copias del nombre
  que puedan divergir entre fuentes (DANE/DIVIPOLA vs. MGN/HDX).

Se invoca siempre como módulo, nunca como script suelto:
`python -m src.extractors.municipios_geometria_extractor` desde la raíz
del repo. Ver `.claude/rules/extractors.md` §6.
"""

from __future__ import annotations

import io
import re
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import geopandas as gpd
import polars as pl
import pyproj
import shapely
import shapely.wkt
from pyogrio.errors import DataLayerError, DataSourceError
from requests import RequestException
from shapely.errors import ShapelyError

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

DATASET_NAME = "municipios_geometria"
SOURCE_URL = (
    "https://data.humdata.org/dataset/50ea7fee-f9af-45a7-8a52-abb9c790a0b6/"
    "resource/32fba556-0109-4d1c-84cb-c8abddf7775b/download/"
    "col-administrative-divisions-shapefiles.zip"
)
SOURCE_NAME = (
    "DANE (Marco Geoestadístico Nacional), vía HDX — Colombia Subnational "
    "Administrative Boundaries (cod-ab-col)"
)
HDX_DATASET_PAGE = "https://data.humdata.org/dataset/cod-ab-col"

# Patrón para localizar el shapefile ADM2 dentro del zip, sin depender del
# sufijo de fecha exacto ("20200416" hoy, puede cambiar en una actualización
# futura del recurso en HDX).
_ADM2_SHP_PATTERN = re.compile(r".*admbnda_adm2.*\.shp$", re.IGNORECASE)
_SHAPEFILE_COMPONENT_EXTENSIONS = (".shp", ".dbf", ".shx", ".prj", ".cpg")

# ~55m en el ecuador — ver docstring del módulo.
SIMPLIFY_TOLERANCE_DEG = 0.0005
WKT_ROUNDING_PRECISION = 6

EXPECTED_MIN_ROWS = 1_100

REUSE_POLICY = ReusePolicy(
    status="open-attribution",
    license="CC BY-IGO 3.0",
    license_url="http://creativecommons.org/licenses/by/3.0/igo/legalcode",
    attribution_required=True,
    redistribution_ok=True,
    summary=(
        "Geometría derivada del Marco Geoestadístico Nacional del DANE, "
        "curada y redistribuida por OCHA (ROLAC/FISS) vía Humanitarian Data "
        "Exchange (HDX), dataset 'cod-ab-col'. CC BY-IGO 3.0: redistribuir "
        "con atribución a DANE y OCHA; a diferencia de CC BY-SA no exige "
        "licenciar las obras derivadas igual. Ver docs/licenses/data_licenses.md."
    ),
)

# Qué cae a fallback: problemas de la FUENTE (red caída, HTTP 4xx/5xx tras
# agotar reintentos, zip corrupto, shapefile ADM2 no localizable dentro del
# zip, o geometría con forma inesperada). Un bug de programación real
# (AttributeError, NameError, etc.) debe reventar. Ver
# `.claude/rules/extractors.md` §1.
EXPECTED_FETCH_FAILURES: tuple[type[Exception], ...] = (
    RequestException,
    zipfile.BadZipFile,
    DataSourceError,
    DataLayerError,
    ShapelyError,
    KeyError,
    ValueError,
    TypeError,
)

# Fallback mínimo para desarrollo offline / CI sin red. NUNCA se publica.
# Geometría real observada en la fuente (2026-10-20), ya simplificada de
# forma agresiva (tolerancia 0.02-0.1°) para que el constante quede legible
# en el código — Medellín y Bogotá (Polygon) y San Andrés (MultiPolygon,
# para ejercitar ese tipo de geometría también offline).
MUNICIPIOS_GEOMETRIA_FALLBACK_DATA: list[dict[str, str]] = [
    {
        "ADM1_PCODE": "CO05",
        "ADM2_PCODE": "CO05001",
        "wkt": (
            "POLYGON ((-75.6697 6.3736, -75.6344 6.3173, -75.4992 6.2953, "
            "-75.4847 6.1909, -75.5324 6.1979, -75.5398 6.1703, -75.6131 6.1988, "
            "-75.68 6.1641, -75.7193 6.3415, -75.714 6.3714, -75.6697 6.3736))"
        ),
    },
    {
        "ADM1_PCODE": "CO11",
        "ADM2_PCODE": "CO11001",
        "wkt": (
            "POLYGON ((-74.0742 4.8365, -74.0056 4.8214, -74.0016 4.6753, "
            "-74.0314 4.6461, -73.9861 4.6291, -74.0053 4.5606, -74.0726 4.5131, "
            "-74.1121 4.4331, -74.0982 4.3456, -74.1527 4.2546, -74.11 4.1819, "
            "-74.1269 4.0485, -74.1507 4.0048, -74.2174 4.0109, -74.3168 3.8813, "
            "-74.2966 3.8189, -74.3356 3.8217, -74.4396 3.7306, -74.3596 3.9137, "
            "-74.3746 3.9859, -74.3299 4.1305, -74.2456 4.1032, -74.218 4.3608, "
            "-74.1736 4.5409, -74.2226 4.6294, -74.1585 4.6628, -74.177 4.7029, "
            "-74.1261 4.7294, -74.0742 4.8365))"
        ),
    },
    {
        "ADM1_PCODE": "CO88",
        "ADM2_PCODE": "CO88001",
        "wkt": (
            "MULTIPOLYGON (((-81.6897 12.5505, -81.6883 12.5506, -81.6885 12.5496, "
            "-81.6897 12.5505)), ((-81.6889 12.553, -81.6886 12.5524, "
            "-81.6892 12.5529, -81.6889 12.553)), ((-81.7323 12.5551, "
            "-81.6871 12.5809, -81.7301 12.4803, -81.7323 12.5551)), "
            "((-81.689 12.5996, -81.6907 12.5993, -81.6898 12.6011, -81.689 12.5996)))"
        ),
    },
]

_SCHEMA = {
    "cod_dpto": pl.Utf8,
    "cod_mpio": pl.Utf8,
    "geom_type": pl.Utf8,
    "area_km2": pl.Float64,
    "geometry_wkt": pl.Utf8,
}

_GEOD = pyproj.Geod(ellps="WGS84")


def _fallback_geodataframe() -> gpd.GeoDataFrame:
    rows = MUNICIPIOS_GEOMETRIA_FALLBACK_DATA
    return gpd.GeoDataFrame(
        {
            "ADM1_PCODE": [r["ADM1_PCODE"] for r in rows],
            "ADM2_PCODE": [r["ADM2_PCODE"] for r in rows],
        },
        geometry=[shapely.wkt.loads(r["wkt"]) for r in rows],
        crs="EPSG:4326",
    )


def _locate_adm2_shapefile(zip_bytes: bytes, extract_dir: Path) -> Path:
    """Localiza y extrae el shapefile ADM2 (municipio) dentro del zip. Lanza
    `KeyError` si no hay exactamente un shapefile ADM2 o le falta algún
    componente — señal de que el recurso de HDX cambió de forma."""
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = zf.namelist()
        shp_matches = [n for n in names if _ADM2_SHP_PATTERN.match(n)]
        if len(shp_matches) != 1:
            raise KeyError(
                f"se esperaba exactamente 1 shapefile ADM2 en el zip, se "
                f"encontraron {len(shp_matches)}: {shp_matches}"
            )
        shp_name = shp_matches[0]
        base = shp_name[: -len(".shp")]
        for ext in _SHAPEFILE_COMPONENT_EXTENSIONS:
            member = base + ext
            if member not in names:
                raise KeyError(f"falta componente del shapefile ADM2 en el zip: {member}")
            zf.extract(member, extract_dir)
        return extract_dir / shp_name


def _normalize(gdf: gpd.GeoDataFrame) -> tuple[pl.DataFrame, int, int]:
    """Devuelve (df, cod_mpio_duplicados, geometrias_invalidas). `gdf` trae
    como mínimo ADM1_PCODE, ADM2_PCODE y geometry en EPSG:4326."""
    if gdf.empty:
        return pl.DataFrame(schema=_SCHEMA), 0, 0

    invalid_mask = gdf.geometry.isna() | gdf.geometry.is_empty
    invalid_count = int(invalid_mask.sum())
    valid = gdf.loc[~invalid_mask].copy()

    valid["cod_dpto"] = valid["ADM1_PCODE"].astype(str).str[-2:].str.zfill(2)
    valid["cod_mpio"] = valid["ADM2_PCODE"].astype(str).str[-5:].str.zfill(5)

    records: list[dict[str, Any]] = []
    for row in valid.itertuples(index=False):
        geom = row.geometry
        area, _perimeter = _GEOD.geometry_area_perimeter(geom)
        simplified = geom.simplify(SIMPLIFY_TOLERANCE_DEG, preserve_topology=True)
        records.append(
            {
                "cod_dpto": row.cod_dpto,
                "cod_mpio": row.cod_mpio,
                "geom_type": simplified.geom_type,
                "area_km2": abs(area) / 1e6,
                "geometry_wkt": shapely.to_wkt(
                    simplified, rounding_precision=WKT_ROUNDING_PRECISION
                ),
            }
        )

    df = pl.DataFrame(records, schema=_SCHEMA)
    total = df.height
    df = df.unique(subset=["cod_mpio"], keep="first")
    duplicates = total - df.height
    return df.sort("cod_mpio"), duplicates, invalid_count


def _fetch_geodataframe() -> tuple[gpd.GeoDataFrame, bytes]:
    zip_bytes = get_bytes(SOURCE_URL, timeout=180)
    with tempfile.TemporaryDirectory() as tmp_dir:
        shp_path = _locate_adm2_shapefile(zip_bytes, Path(tmp_dir))
        gdf = gpd.read_file(shp_path)
    if gdf.crs is not None and gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs(epsg=4326)
    return gdf, zip_bytes


def _normalization_notes(duplicates: int, invalid: int) -> list[str]:
    notes: list[str] = []
    if duplicates > 0:
        notes.append(
            f"{duplicates} filas con cod_mpio duplicado — se conservó la primera "
            "aparición en el shapefile."
        )
    if invalid > 0:
        notes.append(
            f"{invalid} filas con geometría ausente o vacía en la fuente — excluidas, "
            "no se fabrica un polígono de reemplazo."
        )
    return notes


class MunicipiosGeometriaExtractor(BaseExtractor):
    @property
    def dataset_name(self) -> str:
        return DATASET_NAME

    def fetch(self, **kwargs: Any) -> ExtractionResult:
        try:
            gdf, zip_bytes = _fetch_geodataframe()
            df, duplicates, invalid = _normalize(gdf)
            notes = _normalization_notes(duplicates, invalid)
            if df.height < EXPECTED_MIN_ROWS:
                notes.append(
                    f"La fuente devolvió solo {df.height} filas, menos de las "
                    f"{EXPECTED_MIN_ROWS} esperadas como mínimo."
                )

            ensure_staging_directories()
            timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
            raw_path = RAW_DIR / f"municipios_geometria_{timestamp}.zip"
            write_raw_snapshot_atomic(raw_path, zip_bytes)

            return ExtractionResult(
                dataset=DATASET_NAME,
                dataframe=df,
                source_name=SOURCE_NAME,
                source_url=SOURCE_URL,
                source_mode="live",
                source_detail=(
                    "Shapefile ADM2 (municipio) extraído del zip de HDX; geometría "
                    f"simplificada (tolerancia {SIMPLIFY_TOLERANCE_DEG}°) y redondeada "
                    f"a {WKT_ROUNDING_PRECISION} decimales — ver docstring del extractor"
                ),
                reuse_policy=REUSE_POLICY,
                raw_snapshot_path=str(raw_path.relative_to(ROOT_DIR)),
                snapshot_hash=compute_sha256(zip_bytes),
                notes=notes,
            )
        except EXPECTED_FETCH_FAILURES as exc:
            df, duplicates, invalid = _normalize(_fallback_geodataframe())
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
                    *_normalization_notes(duplicates, invalid),
                ],
            )

    def write_staging(self, result: ExtractionResult) -> Path:
        ensure_staging_directories()
        csv_path = STAGING_DIR / "municipios_geometria.csv"
        metadata_path = STAGING_DIR / "municipios_geometria.metadata.json"
        return write_staging_csv_atomic(
            result.dataframe, csv_path, metadata_path, result.to_staging_metadata()
        )


if __name__ == "__main__":
    extractor = MunicipiosGeometriaExtractor()
    outcome = extractor.run()
    print(f"[{DATASET_NAME}] source_mode={outcome.source_mode} rows={outcome.dataframe.height}")
