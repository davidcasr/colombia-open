from src.builders.catalog import build_catalog_entry
from src.registry import load_registry
from src.validation import ValidationResult


def test_catalog_entry_carries_update_frequency_from_registry():
    spec = load_registry()["macroeconomia_trm"]
    entry = build_catalog_entry(
        spec=spec,
        extraction_metadata={"source_url": "https://example.test", "source_mode": "live"},
        validation_result=ValidationResult(
            dataset="macroeconomia_trm", status="ok", record_count=1, errors=[], warnings=[]
        ),
    )
    assert entry["update_frequency"] == spec.update_frequency == "Diaria"
    assert entry["update_frequency_source"] == spec.update_frequency_source
