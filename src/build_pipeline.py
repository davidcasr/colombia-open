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
from src.extractors.delincuencia_hurto_modalidades_extractor import (
    DelincuenciaHurtoModalidadesExtractor,
)
from src.extractors.delincuencia_hurto_personas_extractor import (
    DelincuenciaHurtoPersonasExtractor,
)
from src.extractors.delincuencia_lesiones_personales_extractor import (
    DelincuenciaLesionesPersonalesExtractor,
)
from src.extractors.demografia_extractor import DemografiaExtractor
from src.extractors.divipola_extractor import DivipolaExtractor
from src.extractors.educacion_establecimientos_extractor import (
    EducacionEstablecimientosExtractor,
)
from src.extractors.educacion_saber11_extractor import EducacionSaber11Extractor
from src.extractors.infraestructura_poi_extractor import InfraestructuraPoiExtractor
from src.extractors.municipios_geometria_extractor import MunicipiosGeometriaExtractor
from src.registry import load_registry
from src.validation import (
    validate_delincuencia_hurto_modalidades,
    validate_delincuencia_hurto_personas,
    validate_delincuencia_lesiones_personales,
    validate_demografia,
    validate_departamentos,
    validate_educacion_establecimientos,
    validate_educacion_saber11,
    validate_infraestructura_poi,
    validate_municipios,
    validate_municipios_geometria,
)

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

    # --- demografia: dataset normalizado 1:1 desde staging (sin derive_*) ---
    demografia_extraction = DemografiaExtractor().run()
    demografia_staging_metadata = demografia_extraction.to_staging_metadata()
    demografia_df = demografia_extraction.dataframe
    valid_mpio_codes = set(municipios_df["cod_mpio"].to_list())
    demografia_validation = validate_demografia(
        demografia_df, demografia_staging_metadata, references={"cod_mpio": valid_mpio_codes}
    )
    write_parquet_atomic(demografia_df, NORMALIZED_DIR / "demografia.parquet")
    write_json_atomic(demografia_df, NORMALIZED_DIR / "demografia.json")
    catalog_entries.append(
        build_catalog_entry(
            spec=registry["demografia"],
            extraction_metadata=demografia_staging_metadata,
            validation_result=demografia_validation,
        )
    )

    # --- educacion_establecimientos: dataset normalizado 1:1, sin derive_* ---
    educacion_extraction = EducacionEstablecimientosExtractor().run()
    educacion_staging_metadata = educacion_extraction.to_staging_metadata()
    educacion_df = educacion_extraction.dataframe
    educacion_validation = validate_educacion_establecimientos(
        educacion_df, educacion_staging_metadata, references={"cod_mpio": valid_mpio_codes}
    )
    write_parquet_atomic(educacion_df, NORMALIZED_DIR / "educacion_establecimientos.parquet")
    write_json_atomic(educacion_df, NORMALIZED_DIR / "educacion_establecimientos.json")
    catalog_entries.append(
        build_catalog_entry(
            spec=registry["educacion_establecimientos"],
            extraction_metadata=educacion_staging_metadata,
            validation_result=educacion_validation,
        )
    )

    # --- educacion_saber11: agregado por establecimiento+periodo desde
    # microdato, sin derive_* (la agregación ya ocurre dentro del extractor) ---
    saber11_extraction = EducacionSaber11Extractor().run()
    saber11_staging_metadata = saber11_extraction.to_staging_metadata()
    saber11_df = saber11_extraction.dataframe
    saber11_validation = validate_educacion_saber11(
        saber11_df, saber11_staging_metadata, references={"cod_mpio": valid_mpio_codes}
    )
    write_parquet_atomic(saber11_df, NORMALIZED_DIR / "educacion_saber11.parquet")
    write_json_atomic(saber11_df, NORMALIZED_DIR / "educacion_saber11.json")
    catalog_entries.append(
        build_catalog_entry(
            spec=registry["educacion_saber11"],
            extraction_metadata=saber11_staging_metadata,
            validation_result=saber11_validation,
        )
    )

    # --- delincuencia_hurto_personas: dataset normalizado 1:1, sin derive_* ---
    hurto_extraction = DelincuenciaHurtoPersonasExtractor().run()
    hurto_staging_metadata = hurto_extraction.to_staging_metadata()
    hurto_df = hurto_extraction.dataframe
    hurto_validation = validate_delincuencia_hurto_personas(
        hurto_df, hurto_staging_metadata, references={"cod_mpio": valid_mpio_codes}
    )
    write_parquet_atomic(hurto_df, NORMALIZED_DIR / "delincuencia_hurto_personas.parquet")
    write_json_atomic(hurto_df, NORMALIZED_DIR / "delincuencia_hurto_personas.json")
    catalog_entries.append(
        build_catalog_entry(
            spec=registry["delincuencia_hurto_personas"],
            extraction_metadata=hurto_staging_metadata,
            validation_result=hurto_validation,
        )
    )

    # --- delincuencia_lesiones_personales: 1:1 desde staging (el extractor ya
    # agrega centro poblado -> municipio), sin derive_* ---
    lesiones_extraction = DelincuenciaLesionesPersonalesExtractor().run()
    lesiones_staging_metadata = lesiones_extraction.to_staging_metadata()
    lesiones_df = lesiones_extraction.dataframe
    lesiones_validation = validate_delincuencia_lesiones_personales(
        lesiones_df, lesiones_staging_metadata, references={"cod_mpio": valid_mpio_codes}
    )
    write_parquet_atomic(lesiones_df, NORMALIZED_DIR / "delincuencia_lesiones_personales.parquet")
    write_json_atomic(lesiones_df, NORMALIZED_DIR / "delincuencia_lesiones_personales.json")
    catalog_entries.append(
        build_catalog_entry(
            spec=registry["delincuencia_lesiones_personales"],
            extraction_metadata=lesiones_staging_metadata,
            validation_result=lesiones_validation,
        )
    )

    # --- delincuencia_hurto_modalidades: 1:1 desde staging (el extractor ya
    # agrega centro poblado -> municipio), sin derive_* ---
    modalidades_extraction = DelincuenciaHurtoModalidadesExtractor().run()
    modalidades_staging_metadata = modalidades_extraction.to_staging_metadata()
    modalidades_df = modalidades_extraction.dataframe
    modalidades_validation = validate_delincuencia_hurto_modalidades(
        modalidades_df, modalidades_staging_metadata, references={"cod_mpio": valid_mpio_codes}
    )
    write_parquet_atomic(modalidades_df, NORMALIZED_DIR / "delincuencia_hurto_modalidades.parquet")
    write_json_atomic(modalidades_df, NORMALIZED_DIR / "delincuencia_hurto_modalidades.json")
    catalog_entries.append(
        build_catalog_entry(
            spec=registry["delincuencia_hurto_modalidades"],
            extraction_metadata=modalidades_staging_metadata,
            validation_result=modalidades_validation,
        )
    )

    # --- municipios_geometria: 1:1 desde staging (segunda iteración de
    # divipola/municipios, geometría de un dominio/fuente distinto: HDX, no
    # Socrata), sin derive_* ---
    geometria_extraction = MunicipiosGeometriaExtractor().run()
    geometria_staging_metadata = geometria_extraction.to_staging_metadata()
    geometria_df = geometria_extraction.dataframe
    geometria_validation = validate_municipios_geometria(
        geometria_df, geometria_staging_metadata, references={"cod_mpio": valid_mpio_codes}
    )
    write_parquet_atomic(geometria_df, NORMALIZED_DIR / "municipios_geometria.parquet")
    write_json_atomic(geometria_df, NORMALIZED_DIR / "municipios_geometria.json")
    catalog_entries.append(
        build_catalog_entry(
            spec=registry["municipios_geometria"],
            extraction_metadata=geometria_staging_metadata,
            validation_result=geometria_validation,
        )
    )

    # --- infraestructura_poi: 1:1 desde staging (geocodificado contra la
    # geometría ya extraída arriba), sin derive_* ---
    poi_extraction = InfraestructuraPoiExtractor().run(municipios_geometria=geometria_df)
    poi_staging_metadata = poi_extraction.to_staging_metadata()
    poi_df = poi_extraction.dataframe
    poi_validation = validate_infraestructura_poi(
        poi_df, poi_staging_metadata, references={"cod_mpio": valid_mpio_codes}
    )
    write_parquet_atomic(poi_df, NORMALIZED_DIR / "infraestructura_poi.parquet")
    write_json_atomic(poi_df, NORMALIZED_DIR / "infraestructura_poi.json")
    catalog_entries.append(
        build_catalog_entry(
            spec=registry["infraestructura_poi"],
            extraction_metadata=poi_staging_metadata,
            validation_result=poi_validation,
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
