import polars as pl

from src.builders.datasets import (
    clean_name,
    derive_agro_eva,
    derive_departamentos,
    derive_municipios,
)
from src.extractors.agro_eva_extractor import (
    AGRO_EVA_MINAGRICULTURA_FALLBACK_DATA,
    AGRO_EVA_UPRA_FALLBACK_DATA,
)
from src.extractors.agro_eva_extractor import _normalize as normalize_agro_eva


def _divipola_df() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "cod_dpto": ["05", "05", "11"],
            "nombre_dpto": ["ANTIOQUIA", "ANTIOQUIA", "BOGOTÁ, D.C."],
            "cod_mpio": ["05001", "05002", "11001"],
            "nombre_mpio": ["MEDELLÍN", "ABEJORRAL", "BOGOTÁ, D.C."],
            "tipo_municipio": ["Municipio", "Municipio", "Capital"],
            "longitud": [-75.58, -75.43, -74.08],
            "latitud": [6.25, 5.79, 4.61],
        }
    )


def test_clean_name_strips_accents_and_lowercases():
    assert clean_name("BOGOTÁ, D.C.") == "bogota_d_c"
    assert clean_name("Abejorral") == "abejorral"


def test_derive_departamentos_deduplicates():
    df = derive_departamentos(_divipola_df())
    assert df.height == 2
    assert set(df["cod_dpto"].to_list()) == {"05", "11"}
    assert "nombre_dpto_clean" in df.columns


def test_derive_municipios_keeps_all_rows_and_adds_clean_name():
    df = derive_municipios(_divipola_df())
    assert df.height == 3
    assert "nombre_mpio_clean" in df.columns
    assert df.filter(pl.col("cod_mpio") == "05001")["nombre_mpio_clean"].item() == "medellin"


def test_derive_agro_eva_unifies_crop_name_case_across_series():
    staging, _, _ = normalize_agro_eva(
        AGRO_EVA_UPRA_FALLBACK_DATA, AGRO_EVA_MINAGRICULTURA_FALLBACK_DATA
    )
    df = derive_agro_eva(staging)
    assert df.height == staging.height
    # "Acelga" (UPRA) y "ACELGA" (MinAgricultura) caen en la misma clave.
    acelga = df.filter(pl.col("cultivo_clean") == "acelga")
    assert set(acelga["serie_fuente"].to_list()) == {"upra_2019_2025", "minagricultura_2006_2018"}
    assert df.columns.index("cultivo_clean") == df.columns.index("cultivo") + 1
