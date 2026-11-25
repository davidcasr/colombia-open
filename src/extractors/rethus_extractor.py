"""Extractor del Registro Único Nacional del Talento Humano en Salud
(RETHUS), fuente Ministerio de Salud y Protección Social (MinSalud).

Fuente primaria: API Socrata de datos.gov.co, dataset "Registro Único
Nacional del Talento Humano en Salud - Rethus" (id `my8c-6xkk`). Licencia
CC BY-SA 4.0, atribución MinSalud. Confirmado en vivo el 2026-11-24: 92373
filas, ya agregadas por combinación de (origen del título, tipo de
institución, tipo de programa, perfil profesional, año del acto
administrativo de registro, departamento y municipio de residencia), con
`numeroregistros` como conteo — sin paginación, cabe en un solo request.

https://www.datos.gov.co/resource/my8c-6xkk.json

**Advertencia de alcance — snapshot congelado, no serie viva.** La fuente
declara "Frecuencia de Actualización: Anual" en su metadata, pero
`rowsUpdatedAt`/`publicationDate` del recurso Socrata marcan 2022-05-30 —
las filas no se han refrescado desde esa fecha (confirmado
en vivo 2026-11-24): el año 2022 solo tiene 3429 filas (año parcial, el
más reciente con datos reales) y no hay ninguna fila de 2023 en adelante
salvo el outlier de abajo. El `updatedAt` que muestra el catálogo de
datos.gov.co es un re-touch de metadata, no un refresco de datos. Se
publica igual, documentado explícitamente como snapshot a 2022-05 en
`docs/datasets/rethus.md` — mismo criterio que el snapshot censal de
pobreza municipal en `docs/roadmap/roadmap.md`.

Defecto conocido de la fuente: 4 filas tienen `a_oactoadministrativo`
"2028" (año futuro — error de captura, no un dato real). No se excluyen
(no hay evidencia de qué año correcto debería llevar cada una), pero el
validador las reporta como warning — ver `src/validation/_salud.py`.

`departamentoresidencia`/`municipioresidencia` llegan como strings
"05 - ANTIOQUIA" / "05120 - CÁCERES": el código DIVIPOLA se parsea del
prefijo numérico a string de ancho fijo (2/5 dígitos), nunca a int. Las
~2076 filas (2.2%) con "SIN INFORMACION" en ambos campos (confirmado en
vivo: siempre vienen juntos) se excluyen igual que el "SIN ESTABLECER" de
`delincuencia_hurto_personas` — su conteo queda en las `notes` de cada
build.

Se invoca siempre como módulo, nunca como script suelto:
`python -m src.extractors.rethus_extractor` desde la raíz del repo. Ver
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

DATASET_NAME = "rethus"
SOURCE_URL = "https://www.datos.gov.co/resource/my8c-6xkk.json"
SOURCE_NAME = (
    "Ministerio de Salud y Protección Social (MinSalud) — Registro Único "
    "Nacional del Talento Humano en Salud (RETHUS), agregado (vía datos.gov.co)"
)

# 92373 filas conocidas (2026-11-24), ya agregadas — un solo request alcanza.
# $limit generoso por si la fuente despierta y crece.
FETCH_LIMIT = 150_000
FETCH_TIMEOUT_SECONDS = 60
EXPECTED_MIN_ROWS = 80_000

SOURCE_COLUMNS = [
    "origentitulo",
    "tipoinstitucion",
    "tipoprograma",
    "perfilprofesional",
    "a_oactoadministrativo",
    "departamentoresidencia",
    "municipioresidencia",
    "numeroregistros",
]

SIN_INFORMACION = "SIN INFORMACION"

REUSE_POLICY = ReusePolicy(
    status="open-attribution",
    license="CC BY-SA 4.0",
    license_url="https://www.datos.gov.co/resource/my8c-6xkk",
    attribution_required=True,
    redistribution_ok=True,
    summary=(
        "Datos oficiales del Ministerio de Salud y Protección Social "
        "(MinSalud) publicados en datos.gov.co bajo CC BY-SA 4.0 "
        "(share-alike): redistribuir con atribución a MinSalud y bajo la "
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
# Filas reales observadas en la fuente (2026-11-24): perfiles, programas,
# orígenes de título (local/extranjero) y municipios distintos, más una
# fila "SIN INFORMACION" para ejercitar la exclusión.
RETHUS_FALLBACK_DATA: list[dict[str, Any]] = [
    {
        "origentitulo": "1 - LOCAL",
        "tipoinstitucion": "1 - EDUCACIÓN SUPERIOR",
        "tipoprograma": "UNIVERSITARIA",
        "perfilprofesional": "P07 - MEDICINA",
        "a_oactoadministrativo": "2016",
        "departamentoresidencia": "11 - BOGOTÁ, D.C.",
        "municipioresidencia": "11001 - BOGOTÁ, D.C.",
        "numeroregistros": "3188",
    },
    {
        "origentitulo": "1 - LOCAL",
        "tipoinstitucion": "1 - EDUCACIÓN SUPERIOR",
        "tipoprograma": "UNIVERSITARIA",
        "perfilprofesional": "P11 - PSICOLOGÍA",
        "a_oactoadministrativo": "2020",
        "departamentoresidencia": "11 - BOGOTÁ, D.C.",
        "municipioresidencia": "11001 - BOGOTÁ, D.C.",
        "numeroregistros": "2647",
    },
    {
        "origentitulo": "1 - LOCAL",
        "tipoinstitucion": "1 - EDUCACIÓN SUPERIOR",
        "tipoprograma": "TECNOLOGÍA",
        "perfilprofesional": "SIN INFORMACION",
        "a_oactoadministrativo": "2015",
        "departamentoresidencia": "05 - ANTIOQUIA",
        "municipioresidencia": "05001 - MEDELLÍN",
        "numeroregistros": "2563",
    },
    {
        "origentitulo": "1 - LOCAL",
        "tipoinstitucion": "2 - EDUCACIÓN PARA EL TRABAJO Y EL DESARROLLO HUMANO",
        "tipoprograma": "AUXILIAR",
        "perfilprofesional": "A02 - AUXILIAR EN ENFERMERÍA",
        "a_oactoadministrativo": "2014",
        "departamentoresidencia": "05 - ANTIOQUIA",
        "municipioresidencia": "05120 - CÁCERES",
        "numeroregistros": "1",
    },
    {
        "origentitulo": "2 - EXTRANJERO",
        "tipoinstitucion": "1 - EDUCACIÓN SUPERIOR",
        "tipoprograma": "UNIVERSITARIA",
        "perfilprofesional": "P03 - ENFERMERÍA",
        "a_oactoadministrativo": "2020",
        "departamentoresidencia": "76 - VALLE DEL CAUCA",
        "municipioresidencia": "76520 - PALMIRA",
        "numeroregistros": "1",
    },
    {
        "origentitulo": "2 - EXTRANJERO",
        "tipoinstitucion": "1 - EDUCACIÓN SUPERIOR",
        "tipoprograma": "ESPECIALIZACIÓN",
        "perfilprofesional": "D03 - RADIOLOGÍA E IMÁGENES DIAGNÓSTICAS",
        "a_oactoadministrativo": "2021",
        "departamentoresidencia": "13 - BOLÍVAR",
        "municipioresidencia": "13001 - CARTAGENA",
        "numeroregistros": "1",
    },
    {
        "origentitulo": "1 - LOCAL",
        "tipoinstitucion": "1 - EDUCACIÓN SUPERIOR",
        "tipoprograma": "DOCTORADO",
        "perfilprofesional": "DA99 - DOCTORADO",
        "a_oactoadministrativo": "2020",
        "departamentoresidencia": "05 - ANTIOQUIA",
        "municipioresidencia": "05001 - MEDELLÍN",
        "numeroregistros": "1",
    },
    {
        "origentitulo": "1 - LOCAL",
        "tipoinstitucion": "1 - EDUCACIÓN SUPERIOR",
        "tipoprograma": "UNIVERSITARIA",
        "perfilprofesional": "P08 - NUTRICIÓN Y DIETÉTICA",
        "a_oactoadministrativo": "1989",
        "departamentoresidencia": "76 - VALLE DEL CAUCA",
        "municipioresidencia": "76001 - CALI",
        "numeroregistros": "3",
    },
    {
        "origentitulo": "1 - LOCAL",
        "tipoinstitucion": "2 - EDUCACIÓN PARA EL TRABAJO Y EL DESARROLLO HUMANO",
        "tipoprograma": "AUXILIAR",
        "perfilprofesional": "A02 - AUXILIAR EN ENFERMERÍA",
        "a_oactoadministrativo": "2012",
        "departamentoresidencia": SIN_INFORMACION,
        "municipioresidencia": SIN_INFORMACION,
        "numeroregistros": "26465",
    },
]

_SCHEMA = {
    "cod_dpto": pl.Utf8,
    "nombre_dpto": pl.Utf8,
    "cod_mpio": pl.Utf8,
    "nombre_mpio": pl.Utf8,
    "origen_titulo": pl.Utf8,
    "tipo_institucion": pl.Utf8,
    "tipo_programa": pl.Utf8,
    "perfil_profesional": pl.Utf8,
    "anio_registro": pl.Int32,
    "numero_registros": pl.Int64,
}


def _normalize(rows: list[dict[str, Any]]) -> tuple[pl.DataFrame, int, int]:
    """Devuelve (df, filas_sin_informacion_excluidas, filas_descartadas_por_parseo).

    Vectorizado con Polars: `departamentoresidencia`/`municipioresidencia`
    se parsean del prefijo numérico ("05 - ANTIOQUIA" -> cod_dpto "05")."""
    if not rows:
        return pl.DataFrame(schema=_SCHEMA), 0, 0

    raw = pl.DataFrame(rows, schema=dict.fromkeys(SOURCE_COLUMNS, pl.Utf8))

    # fill_null antes de comparar: una fila con el campo AUSENTE (null) no es
    # lo mismo que una fila con el texto literal "SIN INFORMACION" — sin el
    # fill_null, `null == SIN_INFORMACION` da null y Polars `filter()` la
    # descarta de AMBAS ramas (ni excluded ni skipped la cuentan, se pierde
    # en silencio). Con fill_null, una fila con campo ausente cae a `valid`
    # y queda contabilizada en `skipped` al no poder parsear el código.
    sin_informacion = (pl.col("departamentoresidencia").fill_null("") == SIN_INFORMACION) | (
        pl.col("municipioresidencia").fill_null("") == SIN_INFORMACION
    )
    excluded = raw.filter(sin_informacion).height
    valid = raw.filter(~sin_informacion)

    parsed = valid.with_columns(
        pl.col("departamentoresidencia").str.extract(r"^(\d+)", 1).str.zfill(2).alias("cod_dpto"),
        pl.col("departamentoresidencia")
        .str.extract(r"-\s*(.+)$", 1)
        .str.strip_chars()
        .alias("nombre_dpto"),
        pl.col("municipioresidencia").str.extract(r"^(\d+)", 1).str.zfill(5).alias("cod_mpio"),
        pl.col("municipioresidencia")
        .str.extract(r"-\s*(.+)$", 1)
        .str.strip_chars()
        .alias("nombre_mpio"),
        pl.col("origentitulo").str.strip_chars().alias("origen_titulo"),
        pl.col("tipoinstitucion").str.strip_chars().alias("tipo_institucion"),
        pl.col("tipoprograma").str.strip_chars().alias("tipo_programa"),
        pl.col("perfilprofesional").str.strip_chars().alias("perfil_profesional"),
        pl.col("a_oactoadministrativo").cast(pl.Int32, strict=False).alias("anio_registro"),
        pl.col("numeroregistros").cast(pl.Int64, strict=False).alias("numero_registros"),
    )

    parseable = (
        pl.col("cod_dpto").is_not_null()
        & pl.col("cod_mpio").is_not_null()
        & pl.col("anio_registro").is_not_null()
        & pl.col("numero_registros").is_not_null()
    )
    skipped = parsed.filter(~parseable).height

    records = (
        parsed.filter(parseable)
        .select(
            "cod_dpto",
            "nombre_dpto",
            "cod_mpio",
            "nombre_mpio",
            "origen_titulo",
            "tipo_institucion",
            "tipo_programa",
            "perfil_profesional",
            "anio_registro",
            "numero_registros",
        )
        .cast(_SCHEMA)  # type: ignore[arg-type]
    )
    return records, excluded, skipped


def _fetch_all_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = get_json(
        SOURCE_URL,
        params={"$limit": FETCH_LIMIT},
        timeout=FETCH_TIMEOUT_SECONDS,
    )
    return rows


class RethusExtractor(BaseExtractor):
    @property
    def dataset_name(self) -> str:
        return DATASET_NAME

    def fetch(self, **kwargs: Any) -> ExtractionResult:
        notes: list[str] = [
            "Snapshot congelado: la fuente no se ha refrescado desde "
            "2022-05-30 (rowsUpdatedAt/publicationDate del recurso Socrata), "
            "aunque declara frecuencia de actualización anual. No es una "
            "serie viva — ver docs/datasets/rethus.md."
        ]
        try:
            rows = _fetch_all_rows()
            if len(rows) < EXPECTED_MIN_ROWS:
                notes.append(
                    f"La fuente devolvió solo {len(rows)} filas, menos de las "
                    f"{EXPECTED_MIN_ROWS} esperadas como mínimo."
                )
            df, excluded, skipped = _normalize(rows)
            if excluded > 0:
                notes.append(
                    f"{excluded} filas se excluyeron por traer "
                    f"'{SIN_INFORMACION}' en departamento y municipio de "
                    "residencia (sin código DIVIPOLA posible)."
                )
            if skipped > 0:
                notes.append(
                    f"{skipped} filas se descartaron durante la normalización "
                    "por faltarles un campo indispensable o no parsear."
                )

            ensure_staging_directories()
            timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
            raw_path = RAW_DIR / f"rethus_{timestamp}.json"
            raw_bytes = json.dumps(rows, ensure_ascii=False, indent=2).encode("utf-8")
            write_raw_snapshot_atomic(raw_path, raw_bytes)

            return ExtractionResult(
                dataset=DATASET_NAME,
                dataframe=df,
                source_name=SOURCE_NAME,
                source_url=SOURCE_URL,
                source_mode="live",
                source_detail=(
                    "Socrata API, dataset my8c-6xkk, sin paginación "
                    "(dataset ya agregado, cabe en un solo request)"
                ),
                reuse_policy=REUSE_POLICY,
                raw_snapshot_path=str(raw_path.relative_to(ROOT_DIR)),
                snapshot_hash=compute_sha256(raw_bytes),
                notes=notes,
            )
        except EXPECTED_FETCH_FAILURES as exc:
            df, _excluded, _skipped = _normalize(RETHUS_FALLBACK_DATA)
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
        csv_path = STAGING_DIR / "rethus.csv"
        metadata_path = STAGING_DIR / "rethus.metadata.json"
        return write_staging_csv_atomic(
            result.dataframe, csv_path, metadata_path, result.to_staging_metadata()
        )


if __name__ == "__main__":
    extractor = RethusExtractor()
    outcome = extractor.run()
    print(f"[{DATASET_NAME}] source_mode={outcome.source_mode} rows={outcome.dataframe.height}")
