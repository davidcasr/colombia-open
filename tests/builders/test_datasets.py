import polars as pl

from src.builders.datasets import clean_name, derive_departamentos, derive_municipios


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
