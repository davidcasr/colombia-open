import json

from src.registry import load_registry
from src.registry.dataset_spec import REGISTRY_PATH

# Valores con los que datos.gov.co etiqueta "Frecuencia de Actualización",
# más None para fuentes que no la declaran.
_KNOWN_FREQUENCIES = {"Diaria", "Semanal", "Mensual", "Trimestral", "Semestral", "Anual", None}


def test_every_dataset_declares_update_frequency_explicitly():
    """La clave debe estar presente en cada entrada (aunque sea null): una
    fuente nueva sin decidir su frecuencia falla aquí, no en silencio."""
    raw = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    missing = [name for name, entry in raw.items() if "update_frequency" not in entry]
    assert missing == []


def test_update_frequency_always_has_its_source():
    for name, spec in load_registry().items():
        assert spec.update_frequency in _KNOWN_FREQUENCIES, name
        assert spec.update_frequency_source, f"{name}: falta update_frequency_source"


def test_spec_defaults_to_none_when_absent():
    from src.registry import DatasetSpec

    spec = DatasetSpec.from_dict("x", {"description": "d", "extractor": "e", "source_name": "s"})
    assert spec.update_frequency is None
    assert spec.update_frequency_source is None
