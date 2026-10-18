"""Extractor del directorio único de establecimientos educativos, fuente MEN.

Fuente primaria: API Socrata de datos.gov.co, dataset
"MEN_ESTABLECIMIENTOS_EDUCATIVOS_PREESCOLAR_BÁSICA_Y_MEDIA" (id `cfw5-qzt5`),
publicado por el Ministerio de Educación Nacional, licencia CC BY-SA 4.0.
Confirmado en vivo el 2026-10-18: 606206 filas, años 2015-2025.

https://www.datos.gov.co/Educaci-n/MEN_ESTABLECIMIENTOS_EDUCATIVOS_PREESCOLAR_B-SICA/cfw5-qzt5

Nota de volumen: a diferencia de toda fuente anterior de este proyecto, este
dataset es pesado — ~360MB de JSON crudo, ~7 minutos de descarga paginada.
Es una decisión de alcance explícita (ver docs/datasets/educacion_establecimientos.md):
se publica el historial completo 2015-2025, no solo el año vigente.

Nota de calidad de dato conocida: para el año 2023, el campo `codigo_dane`
(identificador de establecimiento) quedó con muy baja cardinalidad en la
fuente — miles de establecimientos distintos comparten el mismo código
(ej. "105001000000" repetido en decenas de colegios de Medellín). Confirmado
en vivo el 2026-10-18 comparando conteos de filas vs. valores distintos por
año: todos los demás años tienen una relación ~1:1 (ej. 19610 filas / 19599
códigos distintos en 2015), 2023 tiene 416716 filas / solo 3043 códigos
distintos. Es un defecto real de la fuente (MEN/DANE), no un bug de este
extractor — no se fabrica un identificador sintético para taparlo. El
validador (`src/validation/_educacion.py`) lo reporta como warning por año
de baja cardinalidad, no como error de clave duplicada, para no bloquear la
publicación de un dataset que en el resto de sus años es consistente.

Se invoca siempre como módulo, nunca como script suelto:
`python -m src.extractors.educacion_establecimientos_extractor` desde la
raíz del repo (así `src` se resuelve como paquete). Ver
`.claude/rules/extractors.md` §6.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import polars as pl
from requests import RequestException

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
from src.extractors.http_utils import get_json

DATASET_NAME = "educacion_establecimientos"
SOURCE_URL = "https://www.datos.gov.co/resource/cfw5-qzt5.json"
SOURCE_NAME = "MEN — Directorio único de establecimientos educativos (vía datos.gov.co)"

# Dataset grande (606206 filas conocidas, 2026-10-18): se pagina en bloques
# en vez de un solo GET, para que un fallo de red a mitad de camino se
# pueda reintentar por página (tenacity, ver http_utils.get_json) en vez de
# perder una descarga de minutos completa.
PAGE_SIZE = 50_000
# Observado en vivo: ~34s por página de 50k filas. Muy por encima del
# DEFAULT_TIMEOUT (30s) de http_utils — se sobreescribe por request.
PAGE_TIMEOUT_SECONDS = 120
EXPECTED_MIN_ROWS = 500_000

REUSE_POLICY = ReusePolicy(
    status="open-attribution",
    license="CC BY-SA 4.0",
    license_url="https://www.datos.gov.co/resource/cfw5-qzt5",
    attribution_required=True,
    redistribution_ok=True,
    summary=(
        "Datos oficiales del Ministerio de Educación Nacional (MinEducación) "
        "publicados en datos.gov.co bajo CC BY-SA 4.0 (share-alike): "
        "redistribuir con atribución al MEN y bajo la misma licencia. Ver "
        "docs/licenses/data_licenses.md."
    ),
)

# Qué cae a fallback: problemas de la FUENTE (red caída, HTTP 4xx/5xx tras
# agotar reintentos, JSON con forma distinta a la esperada — JSONDecodeError
# hereda de ValueError). Un bug de programación real (AttributeError,
# NameError, etc.) NO está acá a propósito: debe reventar fuerte en vez de
# disfrazarse de "fuente caída". Ver `.claude/rules/extractors.md` §1.
EXPECTED_FETCH_FAILURES: tuple[type[Exception], ...] = (
    RequestException,
    KeyError,
    ValueError,
    TypeError,
)

# Fallback mínimo para desarrollo offline / CI sin red. NUNCA se publica:
# la CI de publicación rechaza cualquier dataset con source_mode="fallback".
# Filas reales observadas en la fuente (2026-10-18): 2 filas limpias de 2015
# y 5 filas de 2023 que reproducen el defecto conocido de codigo_dane de
# baja cardinalidad (3 de ellas comparten el mismo código "105001000000"),
# para que el validador se pueda ejercitar también en modo fallback.
EDUCACION_ESTABLECIMIENTOS_FALLBACK_DATA: list[dict[str, Any]] = [
    {
        "a_o": "2015",
        "cod_dane_departamento": "13",
        "departamento": "BOLÍVAR",
        "cod_secretaria": "4910",
        "secretaria": "CARTAGENA",
        "cod_dane_municipio": "13001",
        "municipio": "Cartagena",
        "codigo_dane": "313001029922",
        "nombre_establecimiento": "INSTITUTO EDUCATIVO NISSI",
        "cod_sector": "1002",
        "sector": "NO_OFICIAL",
        "cod_caracter": "-",
        "caracter": "-",
        "cod_calendario": "52",
        "calendario": "A",
        "direccion": "IND MZ 27 LT 9 - 10 -11",
        "rector": "REYNALDA GUDIÑO GONZALEZ",
        "total_matricula": "187",
        "cantidad_sedes": "1",
    },
    {
        "a_o": "2015",
        "cod_dane_departamento": "47",
        "departamento": "MAGDALENA",
        "cod_secretaria": "4911",
        "secretaria": "SANTA MARTA",
        "cod_dane_municipio": "47001",
        "municipio": "Santa Marta",
        "codigo_dane": "347001051415",
        "nombre_establecimiento": "COLEGIO PERSONITAS DEL FUTURO",
        "cod_sector": "1002",
        "sector": "NO_OFICIAL",
        "cod_caracter": "-",
        "caracter": "-",
        "cod_calendario": "52",
        "calendario": "A",
        "total_matricula": "47",
        "cantidad_sedes": "1",
    },
    {
        "a_o": "2023",
        "cod_dane_departamento": "5",
        "departamento": "Antioquia",
        "cod_secretaria": "3759",
        "secretaria": "MEDELLÍN",
        "cod_dane_municipio": "5001",
        "municipio": "Medellín",
        "codigo_dane": "105001000000",
        "nombre_establecimiento": "INSTITUCION EDUCATIVA LA MILAGROSA",
        "cod_sector": "1001",
        "sector": "OFICIAL",
        "cod_caracter": "2432.000000",
        "caracter": "Técnico/Academico",
        "cod_calendario": "52",
        "calendario": "A",
        "total_matricula": "1872",
        "cantidad_sedes": "2",
    },
    {
        "a_o": "2023",
        "cod_dane_departamento": "5",
        "departamento": "Antioquia",
        "cod_secretaria": "3759",
        "secretaria": "MEDELLÍN",
        "cod_dane_municipio": "5001",
        "municipio": "Medellín",
        "codigo_dane": "105001000000",
        "nombre_establecimiento": "CENTRO EDUCATIVO CARRUSEL DE LA ALEGRIA",
        "cod_sector": "1002",
        "sector": "NO_OFICIAL",
        "cod_caracter": "-",
        "caracter": "-",
        "cod_calendario": "52",
        "calendario": "A",
        "total_matricula": "74",
        "cantidad_sedes": "1",
    },
    {
        "a_o": "2023",
        "cod_dane_departamento": "5",
        "departamento": "Antioquia",
        "cod_secretaria": "3759",
        "secretaria": "MEDELLÍN",
        "cod_dane_municipio": "5001",
        "municipio": "Medellín",
        "codigo_dane": "105001000000",
        "nombre_establecimiento": "INSTITUCION EDUCATIVA REPUBLICA DE URUGUAY",
        "cod_sector": "1001",
        "sector": "OFICIAL",
        "cod_caracter": "2432.000000",
        "caracter": "Técnico/Academico",
        "cod_calendario": "52",
        "calendario": "A",
        "total_matricula": "1353",
        "cantidad_sedes": "1",
    },
    {
        "a_o": "2023",
        "cod_dane_departamento": "5",
        "departamento": "Antioquia",
        "cod_secretaria": "3759",
        "secretaria": "MEDELLÍN",
        "cod_dane_municipio": "5001",
        "municipio": "Medellín",
        "codigo_dane": "105001000000",
        "nombre_establecimiento": "INSTITUCION EDUCATIVA HECTOR ABAD GOMEZ",
        "cod_sector": "1001",
        "sector": "OFICIAL",
        "cod_caracter": "2432.000000",
        "caracter": "Técnico/Academico",
        "cod_calendario": "52",
        "calendario": "A",
        "total_matricula": "2925",
        "cantidad_sedes": "2",
    },
    {
        "a_o": "2023",
        "cod_dane_departamento": "5",
        "departamento": "Antioquia",
        "cod_secretaria": "3759",
        "secretaria": "MEDELLÍN",
        "cod_dane_municipio": "5001",
        "municipio": "Medellín",
        "codigo_dane": "105001000000",
        "nombre_establecimiento": "INSTITUCION EDUCATIVA MANUEL JOSE CAYZEDO",
        "cod_sector": "1001",
        "sector": "OFICIAL",
        "cod_caracter": "2432.000000",
        "caracter": "Técnico/Academico",
        "cod_calendario": "52",
        "calendario": "A",
        "total_matricula": "854",
        "cantidad_sedes": "1",
    },
    {
        "a_o": "2023",
        "cod_dane_departamento": "91",
        "departamento": "Amazonas",
        "cod_secretaria": "3828",
        "secretaria": "AMAZONAS",
        "cod_dane_municipio": "91530",
        "municipio": "Puerto Alegría",
        "codigo_dane": "291407000000",
        "nombre_establecimiento": "BACURI",
        "cod_sector": "1001",
        "sector": "OFICIAL",
        "cod_caracter": "963.000000",
        "caracter": "No Aplica",
        "cod_calendario": "52",
        "calendario": "A",
        "total_matricula": "23",
        "cantidad_sedes": "1",
    },
    {
        # Reproduce el otro defecto conocido de 2023: cod_dane_municipio
        # ausente del JSON (no "null" — el campo directamente no viene).
        # Confirmado en vivo el 2026-10-18: 25/606206 filas, todas 2023.
        "a_o": "2023",
        "cod_dane_departamento": "5",
        "departamento": "Antioquia",
        "cod_secretaria": "7738",
        "codigo_dane": "305266000000",
        "nombre_establecimiento": "COLEGIO GIMNASIO CANTABRIA",
        "cod_sector": "1002",
        "sector": "NO_OFICIAL",
        "cod_caracter": "817.000000",
        "caracter": "Académico",
        "cod_calendario": "52",
        "calendario": "A",
        "total_matricula": "409",
        "cantidad_sedes": "1",
    },
]

_SCHEMA = {
    "anio": pl.Int64,
    "cod_dpto": pl.Utf8,
    "nombre_dpto": pl.Utf8,
    "cod_secretaria": pl.Utf8,
    "nombre_secretaria": pl.Utf8,
    "cod_mpio": pl.Utf8,
    "nombre_mpio": pl.Utf8,
    "codigo_dane_establecimiento": pl.Utf8,
    "nombre_establecimiento": pl.Utf8,
    "cod_sector": pl.Utf8,
    "sector": pl.Utf8,
    "cod_caracter": pl.Int64,
    "caracter": pl.Utf8,
    "cod_calendario": pl.Utf8,
    "calendario": pl.Utf8,
    "direccion": pl.Utf8,
    "barrio_vereda": pl.Utf8,
    "telefono": pl.Utf8,
    "email": pl.Utf8,
    "rector": pl.Utf8,
    "total_matricula": pl.Int64,
    "cantidad_sedes": pl.Int64,
}


def _parse_int(value: Any) -> int | None:
    """Varios campos "number" de Socrata llegan como texto, y al menos uno
    (`cod_caracter`) a veces llega como float-string ('817.000000') y a
    veces como '-' — nunca lanza, devuelve None si no es parseable."""
    if value is None or value == "" or value == "-":
        return None
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return None


def _zfill_or_none(value: Any, width: int) -> str | None:
    """Socrata omite del JSON cualquier campo nulo en vez de mandarlo como
    `null` — confirmado en vivo el 2026-10-18: 25 de 606206 filas (todas
    de 2023, mismo año con el defecto de codigo_dane) no traen
    `cod_dane_municipio` en absoluto. Nunca lanza KeyError: si falta, el
    código queda null en vez de zfillearse sobre texto basura."""
    if value is None:
        return None
    return str(value).zfill(width)


def _build_record(row: dict[str, Any]) -> dict[str, Any]:
    """Puede lanzar (KeyError/ValueError/TypeError) si a esta fila
    específica le falta un campo verdaderamente indispensable (a_o,
    codigo_dane, nombre_establecimiento — sin nulos conocidos en la fuente
    hoy, pero no hay garantía contractual de Socrata de que eso siga así).
    `_normalize()` atrapa esto por fila, no deja que una fila mala tire
    todo un fetch de ~7 minutos a fallback."""
    return {
        "anio": int(row["a_o"]),
        "cod_dpto": _zfill_or_none(row.get("cod_dane_departamento"), 2),
        "nombre_dpto": row.get("departamento"),
        "cod_secretaria": row.get("cod_secretaria"),
        "nombre_secretaria": row.get("secretaria"),
        "cod_mpio": _zfill_or_none(row.get("cod_dane_municipio"), 5),
        "nombre_mpio": row.get("municipio"),
        "codigo_dane_establecimiento": _zfill_or_none(row["codigo_dane"], 12),
        "nombre_establecimiento": row["nombre_establecimiento"],
        "cod_sector": row.get("cod_sector"),
        "sector": row.get("sector"),
        "cod_caracter": _parse_int(row.get("cod_caracter")),
        "caracter": row.get("caracter"),
        "cod_calendario": row.get("cod_calendario"),
        "calendario": row.get("calendario"),
        "direccion": row.get("direccion"),
        "barrio_vereda": row.get("barrio_vereda"),
        "telefono": row.get("telefono"),
        "email": row.get("email"),
        "rector": row.get("rector"),
        "total_matricula": _parse_int(row.get("total_matricula")),
        "cantidad_sedes": _parse_int(row.get("cantidad_sedes")),
    }


def _normalize(rows: list[dict[str, Any]]) -> tuple[pl.DataFrame, int]:
    records: list[dict[str, Any]] = []
    skipped = 0
    for row in rows:
        try:
            records.append(_build_record(row))
        except (KeyError, ValueError, TypeError):
            skipped += 1
    df = pl.DataFrame(records, schema=_SCHEMA)
    return df.sort(["anio", "cod_mpio", "codigo_dane_establecimiento"]), skipped


def _fetch_all_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        page = get_json(
            SOURCE_URL,
            params={"$limit": PAGE_SIZE, "$offset": offset},
            timeout=PAGE_TIMEOUT_SECONDS,
        )
        rows.extend(page)
        if len(page) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
    return rows


class EducacionEstablecimientosExtractor(BaseExtractor):
    @property
    def dataset_name(self) -> str:
        return DATASET_NAME

    def fetch(self, **kwargs: Any) -> ExtractionResult:
        notes: list[str] = []
        try:
            rows = _fetch_all_rows()
            if len(rows) < EXPECTED_MIN_ROWS:
                notes.append(
                    f"La fuente devolvió solo {len(rows)} filas, menos de las "
                    f"{EXPECTED_MIN_ROWS} esperadas como mínimo."
                )
            df, skipped = _normalize(rows)
            if skipped > 0:
                notes.append(
                    f"{skipped} filas se descartaron durante la normalización por "
                    "faltarles un campo indispensable (a_o/codigo_dane/"
                    "nombre_establecimiento)."
                )

            ensure_staging_directories()
            timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
            raw_path = RAW_DIR / f"educacion_establecimientos_{timestamp}.json"
            # Serializado compacto (sin indent) a propósito: con ~600k filas,
            # el indent=2 por defecto de write_raw_snapshot_atomic infla el
            # archivo varias veces sin aportar nada a la auditoría.
            raw_bytes = json.dumps(rows, ensure_ascii=False).encode("utf-8")
            write_raw_snapshot_atomic(raw_path, raw_bytes)

            return ExtractionResult(
                dataset=DATASET_NAME,
                dataframe=df,
                source_name=SOURCE_NAME,
                source_url=SOURCE_URL,
                source_mode="live",
                source_detail=f"Socrata API, dataset cfw5-qzt5, paginado en bloques de {PAGE_SIZE}",
                reuse_policy=REUSE_POLICY,
                raw_snapshot_path=str(raw_path.relative_to(ROOT_DIR)),
                snapshot_hash=compute_sha256(raw_bytes),
                notes=notes,
            )
        except EXPECTED_FETCH_FAILURES as exc:
            df, _skipped = _normalize(EDUCACION_ESTABLECIMIENTOS_FALLBACK_DATA)
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
                    "NO se publica."
                ],
            )

    def write_staging(self, result: ExtractionResult) -> Path:
        ensure_staging_directories()
        csv_path = STAGING_DIR / "educacion_establecimientos.csv"
        metadata_path = STAGING_DIR / "educacion_establecimientos.metadata.json"
        return write_staging_csv_atomic(
            result.dataframe, csv_path, metadata_path, result.to_staging_metadata()
        )


if __name__ == "__main__":
    extractor = EducacionEstablecimientosExtractor()
    outcome = extractor.run()
    print(f"[{DATASET_NAME}] source_mode={outcome.source_mode} rows={outcome.dataframe.height}")
