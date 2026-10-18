"""Orquestador del pipeline: extract -> derive -> validate -> write -> catalog.

Uso: `python -m src.build_pipeline` desde la raíz del repo (equivalente a
`make build`) — siempre como módulo, nunca como script suelto, así `src`
se resuelve como paquete sin manipular `sys.path`.

Para agregar una fuente nueva al pipeline: importa su extractor, llama
`.run()`, deriva los datasets normalizados que produzca, valida cada uno
con su `validate_*` registrado en `src.validation`, escribe parquet/json, y
agrega la entrada correspondiente a `catalog_entries`. La skill
`new-source` genera este bloque por ti.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.builders.catalog import build_catalog_entry, write_dataset_catalog
from src.builders.datasets import derive_departamentos, derive_municipios
from src.builders.formats import write_json_atomic, write_parquet_atomic
from src.extractors.divipola_extractor import DivipolaExtractor
from src.registry import load_registry
from src.validation import validate_departamentos, validate_municipios

ROOT_DIR = Path(__file__).resolve().parent.parent
NORMALIZED_DIR = ROOT_DIR / "data" / "normalized"


def build() -> list[dict[str, Any]]:
    registry = load_registry()
    catalog_entries: list[dict[str, Any]] = []

    # --- divipola: produce dos datasets normalizados (departamentos, municipios) ---
    extraction = DivipolaExtractor().run()
    staging_metadata = extraction.to_staging_metadata()

    departamentos_df = derive_departamentos(extraction.dataframe)
    dept_validation = validate_departamentos(departamentos_df, staging_metadata)
    write_parquet_atomic(departamentos_df, NORMALIZED_DIR / "departamentos.parquet")
    write_json_atomic(departamentos_df, NORMALIZED_DIR / "departamentos.json")
    catalog_entries.append(
        build_catalog_entry(
            spec=registry["departamentos"],
            extraction_metadata=staging_metadata,
            validation_result=dept_validation,
        )
    )

    municipios_df = derive_municipios(extraction.dataframe)
    valid_dept_codes = set(departamentos_df["cod_dpto"].to_list())
    mpio_validation = validate_municipios(
        municipios_df, staging_metadata, references={"cod_dpto": valid_dept_codes}
    )
    write_parquet_atomic(municipios_df, NORMALIZED_DIR / "municipios.parquet")
    write_json_atomic(municipios_df, NORMALIZED_DIR / "municipios.json")
    catalog_entries.append(
        build_catalog_entry(
            spec=registry["municipios"],
            extraction_metadata=staging_metadata,
            validation_result=mpio_validation,
        )
    )

    write_dataset_catalog(catalog_entries)
    return catalog_entries


def main() -> int:
    entries = build()
    had_errors = False
    for entry in entries:
        status = entry["validation_status"]
        marker = "OK " if status == "ok" else "ERROR"
        print(
            f"[{marker}] {entry['dataset']}: {entry['record_count']} filas ({entry['source_mode']})"
        )
        if entry["warnings"]:
            for warning in entry["warnings"]:
                print(f"    warning: {warning}")
        if status != "ok":
            had_errors = True
    return 1 if had_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
