import polars as pl

from src.validation._helpers import dpto_mpio_mismatch_count


def test_dpto_mpio_mismatch_counts_only_contradictions():
    df = pl.DataFrame(
        {
            "cod_dpto": ["05", "81", "25", None, "11"],
            "cod_mpio": ["05001", "85001", "11001", "05001", None],
        }
    )
    assert dpto_mpio_mismatch_count(df) == 2


def test_dpto_mpio_mismatch_missing_columns_is_zero():
    assert dpto_mpio_mismatch_count(pl.DataFrame({"cod_mpio": ["05001"]})) == 0
