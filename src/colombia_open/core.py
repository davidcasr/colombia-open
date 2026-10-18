"""API pública de colombia-open.

    from colombia_open import ColombiaOpen
    hub = ColombiaOpen()
    df = hub.load_polars("municipios")

`ColombiaOpen()` resuelve de dónde vienen los datos en este orden:
1. `catalog_path` explícito.
2. `data_dir` explícito (p. ej. `data_dir="data/normalized"` en un checkout
   de desarrollo con el pipeline ya corrido).
3. `data/normalized/dataset_catalog.json` relativo a la raíz del repo, si
   existe (desarrollo).
4. Si nada de lo anterior existe y `auto_update=True`: descarga y cachea el
   bundle publicado en GitHub Releases (ver `data_manager.py`).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

import polars as pl

from . import data_manager
from .datasets import Dataset
from .exceptions import (
    ColombiaOpenDataError,
    ColombiaOpenDatasetError,
    ColombiaOpenOutputError,
)
from .text import clean_name

JoinStrategy = Literal["inner", "left", "right", "full", "semi", "anti", "cross", "outer"]
_DF_CACHE_MAXSIZE = 8


def _resolve_dataset_name(dataset_name: str | Dataset) -> str:
    if isinstance(dataset_name, Dataset):
        return dataset_name.value
    try:
        return Dataset.from_string(dataset_name).value
    except ValueError as exc:
        raise ColombiaOpenDatasetError(str(exc)) from exc


def _find_dev_catalog() -> Path | None:
    """Detecta un checkout de desarrollo con `make build` ya corrido.

    Deliberadamente NO camina hacia arriba indefinidamente: con un venv
    creado dentro del propio repo (`make bootstrap` -> `.venv/` en la raíz),
    un wheel instalado de verdad (no editable) también queda anidado bajo
    el repo — un walk sin límite encontraría por accidente el
    `data/normalized/` real del repo y trataría cualquier instalación como
    "modo desarrollo", incluso una instalación limpia que debería caer al
    bundle de GitHub Releases. Solo se chequea la profundidad exacta de un
    install editable: `src/colombia_open/core.py` -> `src` -> raíz del repo.
    """
    repo_root_candidate = Path(__file__).resolve().parent.parent.parent
    candidate = repo_root_candidate / "data" / "normalized" / "dataset_catalog.json"
    return candidate if candidate.exists() else None


class ColombiaOpen:
    def __init__(
        self,
        catalog_path: str | Path | None = None,
        *,
        data_dir: str | Path | None = None,
        auto_update: bool = True,
    ) -> None:
        resolved_catalog: Path
        if catalog_path is not None:
            resolved_catalog = Path(catalog_path)
        elif data_dir is not None:
            resolved_catalog = Path(data_dir) / "dataset_catalog.json"
        else:
            dev_catalog = _find_dev_catalog()
            if dev_catalog is not None:
                resolved_catalog = dev_catalog
            else:
                if not auto_update:
                    raise ColombiaOpenDatasetError(
                        "No se encontró data/normalized/dataset_catalog.json y "
                        "auto_update=False. Corre `make build` o pasa data_dir/catalog_path."
                    )
                bundle_dir = data_manager.download_and_cache_bundle()
                resolved_catalog = bundle_dir / "dataset_catalog.json"

        self.catalog_path = resolved_catalog
        self.root_dir = resolved_catalog.parent
        self.catalog = self._load_catalog(resolved_catalog)
        self._df_cache: dict[str, pl.DataFrame] = {}

    @staticmethod
    def _load_catalog(path: Path) -> dict[str, Any]:
        if not path.exists():
            raise ColombiaOpenDatasetError(f"Catálogo no encontrado en: {path}")
        data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        return data

    def list_datasets(self) -> list[str]:
        return [entry["dataset"] for entry in self.catalog.get("datasets", [])]

    def get_dataset(self, dataset_name: str | Dataset) -> dict[str, Any]:
        name = _resolve_dataset_name(dataset_name)
        for entry in self.catalog.get("datasets", []):
            if entry["dataset"] == name:
                result: dict[str, Any] = entry
                return result
        raise ColombiaOpenDatasetError(
            f"Dataset '{name}' no existe. Disponibles: {', '.join(self.list_datasets())}"
        )

    def get_output_path(self, dataset_name: str | Dataset, output_type: str = "parquet") -> Path:
        entry = self.get_dataset(dataset_name)
        outputs = entry.get("outputs", {})
        if output_type not in outputs:
            raise ColombiaOpenOutputError(
                f"Dataset '{entry['dataset']}' no tiene output '{output_type}'. "
                f"Disponibles: {', '.join(outputs) or '(ninguno)'}"
            )
        # Los outputs en el catálogo son nombres de archivo relativos al
        # directorio que contiene dataset_catalog.json — así el mismo
        # catálogo funciona igual en un checkout de desarrollo
        # (data/normalized/) y en el bundle descargado y cacheado.
        path = Path(outputs[output_type])
        return path if path.is_absolute() else self.root_dir / path.name

    def load_polars(self, dataset_name: str | Dataset, *, validate: bool = False) -> pl.DataFrame:
        name = _resolve_dataset_name(dataset_name)
        if name in self._df_cache:
            self._df_cache[name] = self._df_cache.pop(name)  # touch for LRU
        else:
            path = self.get_output_path(name, "parquet")
            try:
                df = pl.read_parquet(path)
            except FileNotFoundError as exc:
                raise ColombiaOpenDatasetError(
                    f"Archivo parquet no encontrado para '{name}': {path}"
                ) from exc
            self._df_cache[name] = df
            while len(self._df_cache) > _DF_CACHE_MAXSIZE:
                self._df_cache.pop(next(iter(self._df_cache)))

        if validate:
            result = self.validate_dataset(name)
            if result["status"] == "error":
                raise ColombiaOpenDataError(
                    f"Validación fallida para '{name}': {'; '.join(result['errors'])}"
                )
        return self._df_cache[name]

    def validate_dataset(self, dataset_name: str | Dataset) -> dict[str, Any]:
        """Re-ejecuta el validador de dominio sobre los datos ya cargados.

        Si el dataset declara `references` en el registro (p. ej. municipios
        referencia departamentos por `cod_dpto`), resuelve esas referencias
        automáticamente cargando el dataset referenciado — así la
        validación de integridad referencial funciona igual aquí que en
        `build_pipeline.py`, sin que este método conozca el dominio de
        ningún dataset en particular.

        Requiere el extra `pipeline` (importa `src.validation`/`src.registry`).
        """
        name = _resolve_dataset_name(dataset_name)
        try:
            from src.registry import load_registry
            from src.validation import VALIDATORS
        except ModuleNotFoundError as exc:
            raise ColombiaOpenDataError(
                "validate_dataset() necesita el extra 'pipeline': "
                "`pip install colombia-open[pipeline]`"
            ) from exc
        if name not in VALIDATORS:
            raise ColombiaOpenDatasetError(f"No hay validador registrado para '{name}'")
        df = self.load_polars(name)
        entry = self.get_dataset(name)

        references: dict[str, set[str]] = {}
        spec = load_registry().get(name)
        if spec is not None:
            for local_column, referenced_dataset in spec.references.items():
                referenced_df = self.load_polars(referenced_dataset)
                references[local_column] = set(referenced_df[local_column].to_list())

        result = VALIDATORS[name](
            df, {"source_mode": entry.get("source_mode")}, references=references or None
        )
        return result.to_dict()

    def provenance(self, dataset_name: str | Dataset) -> dict[str, Any]:
        entry = self.get_dataset(dataset_name)
        return {
            key: entry.get(key)
            for key in (
                "dataset",
                "source_name",
                "source_url",
                "source_mode",
                "refreshed_at_utc",
                "reuse_policy",
            )
        }

    def cross_view(
        self,
        dataset_names: list[str | Dataset],
        *,
        on: str = "cod_mpio",
        how: JoinStrategy = "left",
    ) -> pl.DataFrame:
        if not dataset_names:
            raise ColombiaOpenDatasetError("cross_view() necesita al menos un dataset")
        result = self.load_polars(dataset_names[0])
        for name in dataset_names[1:]:
            other = self.load_polars(name)
            join_cols = [c for c in (on,) if c in result.columns and c in other.columns]
            if not join_cols:
                raise ColombiaOpenDatasetError(
                    f"No se puede cruzar por '{on}': no está en ambos datasets"
                )
            result = result.join(other, on=join_cols, how=how)
        return result

    def resolve_municipios(self, names: list[str]) -> pl.DataFrame:
        """Resuelve nombres de municipio a código DIVIPOLA por coincidencia
        exacta normalizada (sin tildes, minúsculas) — sin fuzzy matching."""
        municipios = self.load_polars("municipios")
        lookup = {clean_name(row["nombre_mpio"]): row for row in municipios.to_dicts()}
        rows = []
        for name in names:
            key = clean_name(name)
            match = lookup.get(key)
            rows.append(
                {
                    "query": name,
                    "matched": match is not None,
                    "cod_mpio": match["cod_mpio"] if match else None,
                    "nombre_mpio": match["nombre_mpio"] if match else None,
                    "cod_dpto": match["cod_dpto"] if match else None,
                }
            )
        return pl.DataFrame(rows)

    def summary(self) -> dict[str, Any]:
        return {
            "datasets": len(self.catalog.get("datasets", [])),
            "generated_at_utc": self.catalog.get("generated_at_utc"),
            "names": self.list_datasets(),
        }
