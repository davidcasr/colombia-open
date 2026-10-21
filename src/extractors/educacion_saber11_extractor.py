"""Extractor de resultados Saber 11 agregados por establecimiento, fuente ICFES.

Fuente primaria: API Socrata de datos.gov.co, dataset "Resultados únicos
Saber 11" (id `kgxf-xxbe`), publicado por el Instituto Colombiano para la
Evaluación de la Educación (ICFES), licencia CC BY-SA 4.0. Confirmado en
vivo el 2026-10-21: 7109704 filas de microdato por estudiante, 2010-2022,
22 periodos de aplicación (formato `AAAAP`, ej. "20194").

https://www.datos.gov.co/resource/kgxf-xxbe.json

Decisión de alcance (discutida con David, ver conversación de la sesión
que agregó esta fuente):

- **Se agrega por `(codigo_dane_establecimiento, periodo)`, no por
  municipio ni se publica microdato.** Agregar solo por municipio deja el
  resultado "suelto" — sin forma de relacionarlo con un colegio específico
  de `educacion_establecimientos`. Agregando por establecimiento,
  `codigo_dane_establecimiento` es join key directa hacia
  `educacion_establecimientos.codigo_dane_establecimiento` (mismo formato
  de 12 dígitos, mismo nivel "institución" — no "sede": confirmado en vivo,
  12125 instituciones distintas en 12 años, consistente con el total real
  de IE del país, muy por debajo de las ~13691 sedes distintas que trae un
  campo aparte, `cole_cod_dane_sede`, que no se usa aquí).
- **Nunca se publica microdato por estudiante** — ni por volumen (7.1M
  filas) ni por ser información sensible de datos personales/familiares
  (`fami_*`, fecha de nacimiento). Variables socioeconómicas quedan fuera
  de esta primera iteración — candidata a segunda iteración si hay
  demanda, documentada aquí en vez de implementada especulativamente.
- **La fuente solo reporta `punt_matematicas`/`punt_ingles` antes del
  periodo `20142`** — la reforma de la prueba de 2014 agregó
  `punt_global`/`punt_lectura_critica`/`punt_sociales_ciudadanas`/
  `punt_c_naturales`. Confirmado en vivo: la escala de matemáticas/inglés
  SÍ es comparable antes y después de la reforma (promedio ~50 en 2010 y
  ~51 en 2016, misma escala ~0-100) — por eso se publica el rango completo
  2010-2022 en vez de truncar a solo el periodo post-reforma, y los 4
  campos nuevos quedan `null` (no fabricados) en los periodos viejos.

Nota de paginación — distinta a los demás extractores del proyecto: con
7.1M filas, paginar con `$offset` se vuelve progresivamente más lento
(confirmado en vivo: una página de 100k filas tardó 87.5s en offset~7M,
contra 2.7s en offset=0). Se usa **keyset pagination** vía el pseudo-campo
`:id` de Socrata (`$where=:id > 'ultimo_id'&$order=:id`) en vez de
`$offset` — confirmado en vivo: 12.25s para una página de 100k a la misma
profundidad (~7x más rápido, y no degrada con la profundidad). No
reemplaces esto por `$offset` sin volver a medir.

Se invoca siempre como módulo, nunca como script suelto:
`python -m src.extractors.educacion_saber11_extractor` desde la raíz del
repo. Ver `.claude/rules/extractors.md` §6.
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

DATASET_NAME = "educacion_saber11"
SOURCE_URL = "https://www.datos.gov.co/resource/kgxf-xxbe.json"
SOURCE_NAME = "ICFES — Resultados Saber 11, agregado por establecimiento (vía datos.gov.co)"

# Solo los campos que esta fuente necesita — ni microdato de estudiante
# (privacidad) ni socioeconómicos (fuera de alcance v1, ver docstring).
_SELECT_FIELDS = (
    "periodo,cole_cod_dane_establecimiento,cole_cod_depto_ubicacion,"
    "cole_cod_mcpio_ubicacion,cole_naturaleza,punt_matematicas,punt_ingles,"
    "punt_lectura_critica,punt_sociales_ciudadanas,punt_c_naturales,punt_global"
)

# Keyset pagination (ver docstring del módulo) — no offset. 100k filas por
# página observado en vivo en ~12s con este método, independiente de la
# profundidad.
PAGE_SIZE = 100_000
PAGE_TIMEOUT_SECONDS = 120
EXPECTED_MIN_RAW_ROWS = 7_000_000
EXPECTED_MIN_ROWS = 90_000

REUSE_POLICY = ReusePolicy(
    status="open-attribution",
    license="CC BY-SA 4.0",
    license_url="https://www.datos.gov.co/resource/kgxf-xxbe",
    attribution_required=True,
    redistribution_ok=True,
    summary=(
        "Datos oficiales del Instituto Colombiano para la Evaluación de la "
        "Educación (ICFES) publicados en datos.gov.co bajo CC BY-SA 4.0 "
        "(share-alike): redistribuir con atribución al ICFES y bajo la "
        "misma licencia. Ver docs/licenses/data_licenses.md."
    ),
)

# Qué cae a fallback: problemas de la FUENTE (red caída, HTTP 4xx/5xx tras
# reintentos, JSON con forma inesperada). Un bug de programación real debe
# reventar. Ver `.claude/rules/extractors.md` §1.
EXPECTED_FETCH_FAILURES: tuple[type[Exception], ...] = (
    RequestException,
    KeyError,
    ValueError,
    TypeError,
)

# Fallback mínimo para desarrollo offline / CI sin red. NUNCA se publica.
# Filas reales observadas en la fuente (2026-10-21): 3 de periodos previos
# a la reforma de 2014 (solo matemáticas/inglés), 4 de un periodo moderno
# (2 pares de "mismo establecimiento, 2 estudiantes" para ejercitar el
# promedio y el conteo), y 2 sin `cole_cod_dane_establecimiento` (defecto
# real de la fuente, ~3377 de 7.1M filas) para ejercitar la exclusión.
EDUCACION_SABER11_FALLBACK_DATA: list[dict[str, Any]] = [
    {
        "periodo": "20131",
        "cole_cod_dane_establecimiento": "311848000812",
        "cole_cod_depto_ubicacion": "11",
        "cole_cod_mcpio_ubicacion": "11001",
        "cole_naturaleza": "NO OFICIAL",
        "punt_matematicas": "88",
        "punt_ingles": "94",
    },
    {
        "periodo": "20131",
        "cole_cod_dane_establecimiento": "376001033859",
        "cole_cod_depto_ubicacion": "76",
        "cole_cod_mcpio_ubicacion": "76001",
        "cole_naturaleza": "NO OFICIAL",
        "punt_matematicas": "57",
        "punt_ingles": "68",
    },
    {
        "periodo": "20131",
        "cole_cod_dane_establecimiento": "311001107599",
        "cole_cod_depto_ubicacion": "11",
        "cole_cod_mcpio_ubicacion": "11001",
        "cole_naturaleza": "NO OFICIAL",
        "punt_matematicas": "70",
        "punt_ingles": "77",
    },
    {
        "periodo": "20194",
        "cole_cod_dane_establecimiento": "141016000305",
        "cole_cod_depto_ubicacion": "41",
        "cole_cod_mcpio_ubicacion": "41016",
        "cole_naturaleza": "OFICIAL",
        "punt_matematicas": "66",
        "punt_ingles": "71",
        "punt_lectura_critica": "69",
        "punt_sociales_ciudadanas": "70",
        "punt_c_naturales": "65",
        "punt_global": "339",
    },
    {
        "periodo": "20194",
        "cole_cod_dane_establecimiento": "141016000305",
        "cole_cod_depto_ubicacion": "41",
        "cole_cod_mcpio_ubicacion": "41016",
        "cole_naturaleza": "OFICIAL",
        "punt_matematicas": "66",
        "punt_ingles": "71",
        "punt_lectura_critica": "69",
        "punt_sociales_ciudadanas": "70",
        "punt_c_naturales": "65",
        "punt_global": "339",
    },
    {
        "periodo": "20194",
        "cole_cod_dane_establecimiento": "311001109885",
        "cole_cod_depto_ubicacion": "11",
        "cole_cod_mcpio_ubicacion": "11001",
        "cole_naturaleza": "NO OFICIAL",
        "punt_matematicas": "45",
        "punt_ingles": "56",
        "punt_lectura_critica": "35",
        "punt_sociales_ciudadanas": "27",
        "punt_c_naturales": "27",
        "punt_global": "176",
    },
    {
        "periodo": "20194",
        "cole_cod_dane_establecimiento": "311001109885",
        "cole_cod_depto_ubicacion": "11",
        "cole_cod_mcpio_ubicacion": "11001",
        "cole_naturaleza": "NO OFICIAL",
        "punt_matematicas": "45",
        "punt_ingles": "56",
        "punt_lectura_critica": "35",
        "punt_sociales_ciudadanas": "27",
        "punt_c_naturales": "27",
        "punt_global": "176",
    },
    {
        "periodo": "20122",
        "cole_cod_depto_ubicacion": "23",
        "cole_cod_mcpio_ubicacion": "23001",
        "cole_naturaleza": "NO OFICIAL",
        "punt_matematicas": "39",
        "punt_ingles": "38",
    },
    {
        "periodo": "20112",
        "cole_cod_depto_ubicacion": "76",
        "cole_cod_mcpio_ubicacion": "76001",
        "cole_naturaleza": "NO OFICIAL",
        "punt_matematicas": "45",
        "punt_ingles": "41",
    },
]

_RAW_SCHEMA = {
    "periodo": pl.Utf8,
    "codigo_dane_establecimiento": pl.Utf8,
    "cod_dpto": pl.Utf8,
    "cod_mpio": pl.Utf8,
    "naturaleza": pl.Utf8,
    "punt_matematicas": pl.Float64,
    "punt_ingles": pl.Float64,
    "punt_lectura_critica": pl.Float64,
    "punt_sociales_ciudadanas": pl.Float64,
    "punt_c_naturales": pl.Float64,
    "punt_global": pl.Float64,
}

PRIMARY_KEY = ["codigo_dane_establecimiento", "periodo"]

_OUTPUT_COLUMNS = [
    "codigo_dane_establecimiento",
    "periodo",
    "anio",
    "cod_dpto",
    "cod_mpio",
    "naturaleza",
    "n_estudiantes",
    "prom_matematicas",
    "prom_ingles",
    "prom_lectura_critica",
    "prom_sociales_ciudadanas",
    "prom_c_naturales",
    "prom_global",
]

_SCHEMA = {
    "codigo_dane_establecimiento": pl.Utf8,
    "periodo": pl.Utf8,
    "anio": pl.Int64,
    "cod_dpto": pl.Utf8,
    "cod_mpio": pl.Utf8,
    "naturaleza": pl.Utf8,
    "n_estudiantes": pl.Int64,
    "prom_matematicas": pl.Float64,
    "prom_ingles": pl.Float64,
    "prom_lectura_critica": pl.Float64,
    "prom_sociales_ciudadanas": pl.Float64,
    "prom_c_naturales": pl.Float64,
    "prom_global": pl.Float64,
}


def _parse_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _zfill_or_none(value: Any, width: int) -> str | None:
    """Socrata omite del JSON cualquier campo nulo en vez de mandarlo como
    `null` — confirmado en vivo el 2026-10-21: ~3377 de 7.1M filas no traen
    `cole_cod_dane_establecimiento` en absoluto. Nunca lanza KeyError."""
    if value is None:
        return None
    return str(value).zfill(width)


def _build_record(row: dict[str, Any]) -> dict[str, Any]:
    """Puede lanzar (KeyError/ValueError/TypeError) si a esta fila le falta
    `periodo` — sin nulos conocidos en la fuente hoy, pero sin garantía
    contractual de Socrata de que eso siga así. `_normalize()` lo atrapa
    por fila, no deja que una fila mala tire todo el fetch a fallback."""
    return {
        "periodo": row["periodo"],
        "codigo_dane_establecimiento": _zfill_or_none(row.get("cole_cod_dane_establecimiento"), 12),
        "cod_dpto": _zfill_or_none(row.get("cole_cod_depto_ubicacion"), 2),
        "cod_mpio": _zfill_or_none(row.get("cole_cod_mcpio_ubicacion"), 5),
        "naturaleza": row.get("cole_naturaleza"),
        "punt_matematicas": _parse_float(row.get("punt_matematicas")),
        "punt_ingles": _parse_float(row.get("punt_ingles")),
        "punt_lectura_critica": _parse_float(row.get("punt_lectura_critica")),
        "punt_sociales_ciudadanas": _parse_float(row.get("punt_sociales_ciudadanas")),
        "punt_c_naturales": _parse_float(row.get("punt_c_naturales")),
        "punt_global": _parse_float(row.get("punt_global")),
    }


def _most_frequent(values: pl.Expr) -> pl.Expr:
    """Valor más frecuente de un grupo; desempata por orden alfabético para
    que el resultado sea determinista entre builds. `cod_dpto`/`cod_mpio`/
    `naturaleza` deberían ser constantes por establecimiento, pero no hay
    garantía contractual de la fuente — mismo patrón que los extractores de
    delincuencia."""
    return values.drop_nulls().mode().sort().first()


def _normalize(rows: list[dict[str, Any]]) -> tuple[pl.DataFrame, int, int]:
    """Devuelve (df_agregado_por_establecimiento_y_periodo,
    filas_sin_establecimiento_o_municipio, filas_descartadas_por_parseo).
    Vectorizado con Polars: la fuente tiene ~7.1 millones de filas."""
    if not rows:
        return pl.DataFrame(schema=_SCHEMA), 0, 0

    records: list[dict[str, Any]] = []
    skipped = 0
    for row in rows:
        try:
            records.append(_build_record(row))
        except (KeyError, ValueError, TypeError):
            skipped += 1
    raw = pl.DataFrame(records, schema=_RAW_SCHEMA)

    sin_establecimiento = (
        pl.col("codigo_dane_establecimiento").is_null() | pl.col("cod_mpio").is_null()
    )
    excluded = raw.filter(sin_establecimiento).height
    valid = raw.filter(~sin_establecimiento)

    df = (
        valid.group_by(PRIMARY_KEY)
        .agg(
            _most_frequent(pl.col("cod_dpto")).alias("cod_dpto"),
            _most_frequent(pl.col("cod_mpio")).alias("cod_mpio"),
            _most_frequent(pl.col("naturaleza")).alias("naturaleza"),
            pl.len().alias("n_estudiantes"),
            pl.col("punt_matematicas").mean().alias("prom_matematicas"),
            pl.col("punt_ingles").mean().alias("prom_ingles"),
            pl.col("punt_lectura_critica").mean().alias("prom_lectura_critica"),
            pl.col("punt_sociales_ciudadanas").mean().alias("prom_sociales_ciudadanas"),
            pl.col("punt_c_naturales").mean().alias("prom_c_naturales"),
            pl.col("punt_global").mean().alias("prom_global"),
        )
        .with_columns(pl.col("periodo").str.slice(0, 4).cast(pl.Int64).alias("anio"))
        .select(_OUTPUT_COLUMNS)
        .cast(_SCHEMA)  # type: ignore[arg-type]
        .sort(PRIMARY_KEY)
    )
    return df, excluded, skipped


def _fetch_all_rows() -> list[dict[str, Any]]:
    """Keyset pagination vía `:id` — ver docstring del módulo para por qué
    NO es `$offset`."""
    rows: list[dict[str, Any]] = []
    last_id: str | None = None
    while True:
        params: dict[str, Any] = {
            "$select": f"{_SELECT_FIELDS},:id",
            "$order": ":id",
            "$limit": PAGE_SIZE,
        }
        if last_id is not None:
            params["$where"] = f":id > '{last_id}'"
        page = get_json(SOURCE_URL, params=params, timeout=PAGE_TIMEOUT_SECONDS)
        if not page:
            break
        rows.extend(page)
        last_id = page[-1][":id"]
        if len(page) < PAGE_SIZE:
            break
    return rows


def _normalization_notes(raw_count: int, excluded: int, skipped: int) -> list[str]:
    notes: list[str] = []
    if raw_count < EXPECTED_MIN_RAW_ROWS:
        notes.append(
            f"La fuente devolvió solo {raw_count} filas de microdato, menos de las "
            f"{EXPECTED_MIN_RAW_ROWS} esperadas como mínimo."
        )
    if excluded > 0:
        notes.append(
            f"{excluded} filas de microdato excluidas antes de agregar por no traer "
            "cole_cod_dane_establecimiento o cole_cod_mcpio_ubicacion; ver "
            "docs/datasets/educacion_saber11.md."
        )
    if skipped > 0:
        notes.append(
            f"{skipped} filas se descartaron durante la normalización por faltarles "
            "el campo periodo."
        )
    return notes


class EducacionSaber11Extractor(BaseExtractor):
    @property
    def dataset_name(self) -> str:
        return DATASET_NAME

    def fetch(self, **kwargs: Any) -> ExtractionResult:
        try:
            rows = _fetch_all_rows()
            df, excluded, skipped = _normalize(rows)
            notes = _normalization_notes(len(rows), excluded, skipped)
            if df.height < EXPECTED_MIN_ROWS:
                notes.append(
                    f"El dataset agregado quedó en {df.height} filas, menos de las "
                    f"{EXPECTED_MIN_ROWS} esperadas como mínimo."
                )

            ensure_staging_directories()
            timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
            raw_path = RAW_DIR / f"educacion_saber11_{timestamp}.json"
            # Compacto (sin indent): ~7.1M filas de microdato, aunque ya
            # recortadas a solo los campos que este extractor necesita.
            raw_bytes = json.dumps(rows, ensure_ascii=False).encode("utf-8")
            write_raw_snapshot_atomic(raw_path, raw_bytes)

            return ExtractionResult(
                dataset=DATASET_NAME,
                dataframe=df,
                source_name=SOURCE_NAME,
                source_url=SOURCE_URL,
                source_mode="live",
                source_detail=(
                    "Socrata API, dataset kgxf-xxbe, keyset pagination vía :id en "
                    f"bloques de {PAGE_SIZE}; agregado de microdato por estudiante a "
                    "(codigo_dane_establecimiento, periodo)"
                ),
                reuse_policy=REUSE_POLICY,
                raw_snapshot_path=str(raw_path.relative_to(ROOT_DIR)),
                snapshot_hash=compute_sha256(raw_bytes),
                notes=notes,
            )
        except EXPECTED_FETCH_FAILURES as exc:
            df, excluded, skipped = _normalize(EDUCACION_SABER11_FALLBACK_DATA)
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
                    *_normalization_notes(len(EDUCACION_SABER11_FALLBACK_DATA), excluded, skipped),
                ],
            )

    def write_staging(self, result: ExtractionResult) -> Path:
        ensure_staging_directories()
        csv_path = STAGING_DIR / "educacion_saber11.csv"
        metadata_path = STAGING_DIR / "educacion_saber11.metadata.json"
        return write_staging_csv_atomic(
            result.dataframe, csv_path, metadata_path, result.to_staging_metadata()
        )


if __name__ == "__main__":
    extractor = EducacionSaber11Extractor()
    outcome = extractor.run()
    print(f"[{DATASET_NAME}] source_mode={outcome.source_mode} rows={outcome.dataframe.height}")
