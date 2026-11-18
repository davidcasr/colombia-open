import json

import polars as pl
import pytest

from colombia_open import ColombiaOpen
from colombia_open.exceptions import ColombiaOpenDatasetError
from colombia_open.resolve import MUNICIPIO_ALIASES, resolve_municipio_names

# Filas reales de DIVIPOLA (nombres y códigos tal como vienen en el
# dataset `municipios` publicado), incluidos nombres repetidos entre
# departamentos.
_ROWS = [
    ("05", "ANTIOQUIA", "05001", "MEDELLÍN"),
    ("05", "ANTIOQUIA", "05615", "RIONEGRO"),
    ("68", "SANTANDER", "68615", "RIONEGRO"),
    ("05", "ANTIOQUIA", "05400", "LA UNIÓN"),
    ("52", "NARIÑO", "52399", "LA UNIÓN"),
    ("70", "SUCRE", "70400", "LA UNIÓN"),
    ("76", "VALLE DEL CAUCA", "76400", "LA UNIÓN"),
    ("76", "VALLE DEL CAUCA", "76001", "SANTIAGO DE CALI"),
    ("76", "VALLE DEL CAUCA", "76111", "GUADALAJARA DE BUGA"),
    ("11", "BOGOTÁ, D.C.", "11001", "BOGOTÁ, D.C."),
    ("13", "BOLÍVAR", "13001", "CARTAGENA DE INDIAS"),
    ("13", "BOLÍVAR", "13468", "SANTA CRUZ DE MOMPOX"),
    ("18", "CAQUETÁ", "18150", "CARTAGENA DEL CHAIRÁ"),
    ("54", "NORTE DE SANTANDER", "54001", "SAN JOSÉ DE CÚCUTA"),
    ("47", "MAGDALENA", "47001", "SANTA MARTA"),
    ("25", "CUNDINAMARCA", "25843", "VILLA DE SAN DIEGO DE UBATÉ"),
    ("70", "SUCRE", "70820", "SANTIAGO DE TOLÚ"),
    ("70", "SUCRE", "70823", "SAN JOSÉ DE TOLUVIEJO"),
    ("52", "NARIÑO", "52835", "SAN ANDRÉS DE TUMACO"),
    ("52", "NARIÑO", "52001", "PASTO"),
]


@pytest.fixture
def municipios() -> pl.DataFrame:
    return pl.DataFrame(
        _ROWS, schema=["cod_dpto", "nombre_dpto", "cod_mpio", "nombre_mpio"], orient="row"
    )


def _one(df: pl.DataFrame) -> dict:
    assert df.height == 1
    return df.row(0, named=True)


def test_exact_match(municipios):
    row = _one(resolve_municipio_names(municipios, ["Medellín"]))
    assert row["matched"] is True
    assert row["match_type"] == "exact"
    assert row["cod_mpio"] == "05001"
    assert row["candidates"] == []


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("Cali", "76001"),
        ("cali", "76001"),
        ("Bogotá", "11001"),
        ("BOGOTA", "11001"),
        ("Bogotá DC", "11001"),
        ("Bogotá, D.C.", "11001"),  # oficial: exact, no alias
        ("Cartagena", "13001"),
        ("Cartagena de Indias", "13001"),
        ("Cúcuta", "54001"),
        ("Santa Marta", "47001"),
        ("Mompós", "13468"),
        ("Ubaté", "25843"),
        ("Buga", "76111"),
        ("Tolú", "70820"),
        ("Tumaco", "52835"),
    ],
)
def test_common_names_resolve(municipios, query, expected):
    row = _one(resolve_municipio_names(municipios, [query]))
    assert row["matched"] is True, row
    assert row["cod_mpio"] == expected


def test_alias_reports_match_type(municipios):
    row = _one(resolve_municipio_names(municipios, ["Cali"]))
    assert row["match_type"] == "alias"
    assert row["nombre_mpio"] == "SANTIAGO DE CALI"


def test_repeated_name_is_ambiguous_never_picked_silently(municipios):
    row = _one(resolve_municipio_names(municipios, ["Rionegro"]))
    assert row["matched"] is False
    assert row["match_type"] == "ambiguous"
    assert row["cod_mpio"] is None
    assert sorted(c.split()[0] for c in row["candidates"]) == ["05615", "68615"]


def test_four_way_ambiguity_lists_all_candidates(municipios):
    row = _one(resolve_municipio_names(municipios, ["La Unión"]))
    assert row["match_type"] == "ambiguous"
    assert len(row["candidates"]) == 4


@pytest.mark.parametrize("dpto", ["Antioquia", "ANTIOQUIA", "05", "5"])
def test_departamento_disambiguates(municipios, dpto):
    row = _one(resolve_municipio_names(municipios, ["Rionegro"], departamento=dpto))
    assert row["matched"] is True
    assert row["cod_mpio"] == "05615"


def test_per_name_departamento_via_tuple(municipios):
    df = resolve_municipio_names(
        municipios, [("Rionegro", "Santander"), ("La Unión", "Nariño"), "Cali"]
    )
    assert df["cod_mpio"].to_list() == ["68615", "52399", "76001"]
    assert df["departamento"].to_list() == ["Santander", "Nariño", None]


def test_departamento_alias(municipios):
    row = _one(resolve_municipio_names(municipios, ["La Unión"], departamento="Valle"))
    assert row["cod_mpio"] == "76400"


def test_departamento_excludes_wrong_alias(municipios):
    """`Cartagena` es alias de Cartagena de Indias (Bolívar); filtrado a
    Caquetá no debe devolverlo — y sí sugerir Cartagena del Chairá."""
    row = _one(resolve_municipio_names(municipios, ["Cartagena"], departamento="Caquetá"))
    assert row["matched"] is False
    assert row["match_type"] == "not_found"
    assert any("18150" in c for c in row["candidates"])


def test_not_found_gives_suggestions_but_no_match(municipios):
    row = _one(resolve_municipio_names(municipios, ["Medelin"]))
    assert row["matched"] is False
    assert row["match_type"] == "not_found"
    assert row["cod_mpio"] is None
    assert any("05001" in c for c in row["candidates"])


def test_unknown_departamento_raises(municipios):
    with pytest.raises(ColombiaOpenDatasetError, match="no reconocido"):
        resolve_municipio_names(municipios, ["Rionegro"], departamento="Narnia")


def test_alias_to_missing_code_is_ignored(municipios):
    """Un alias cuyo código no está en el dataset no inventa un municipio."""
    without_cali = municipios.filter(pl.col("cod_mpio") != "76001")
    row = _one(resolve_municipio_names(without_cali, ["Cali"]))
    assert row["matched"] is False


def test_empty_input_returns_typed_empty_frame(municipios):
    df = resolve_municipio_names(municipios, [])
    assert df.height == 0
    assert df.schema["candidates"] == pl.List(pl.Utf8)


def test_aliases_are_clean_keys_and_valid_codes():
    from colombia_open.text import clean_name

    for key, code in MUNICIPIO_ALIASES.items():
        assert clean_name(key) == key
        assert len(code) == 5 and code.isdigit()


def test_hub_method_joins_departamento_names_when_missing(tmp_path):
    """El método público funciona aunque `municipios` no traiga
    nombre_dpto (lo toma de `departamentos`)."""
    pl.DataFrame(
        {"cod_dpto": ["05", "68"], "nombre_dpto": ["ANTIOQUIA", "SANTANDER"]}
    ).write_parquet(tmp_path / "departamentos.parquet")
    pl.DataFrame(
        {"cod_dpto": ["05", "68"], "cod_mpio": ["05615", "68615"], "nombre_mpio": ["RIONEGRO"] * 2}
    ).write_parquet(tmp_path / "municipios.parquet")
    catalog = {
        "datasets": [
            {"dataset": n, "outputs": {"parquet": f"{n}.parquet"}}
            for n in ("departamentos", "municipios")
        ]
    }
    (tmp_path / "dataset_catalog.json").write_text(json.dumps(catalog), encoding="utf-8")

    hub = ColombiaOpen(data_dir=tmp_path)
    row = _one(hub.resolve_municipios(["Rionegro"], departamento="Antioquia"))
    assert row["cod_mpio"] == "05615"
    ambiguous = _one(hub.resolve_municipios(["Rionegro"]))
    assert "05615 RIONEGRO (ANTIOQUIA)" in ambiguous["candidates"]
