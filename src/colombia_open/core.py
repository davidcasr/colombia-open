"""API pública de colombia-open.

    from colombia_open import ColombiaOpen
    hub = ColombiaOpen()
    df = hub.load_polars("municipios")

`ColombiaOpen()` resuelve de dónde vienen los datos en este orden:
1. `catalog_path` explícito.
2. `data_dir` explícito (p. ej. `data_dir="data/normalized"` en un checkout
   de desarrollo con el pipeline ya corrido).
3. Variable de entorno `COLOMBIA_OPEN_DATA_DIR` (mirror/offline: un
   bundle ya descomprimido).
4. `data/normalized/dataset_catalog.json` relativo a la raíz del repo, si
   existe (desarrollo).
5. Si nada de lo anterior existe y `auto_update=True`: descarga y cachea el
   bundle publicado en GitHub Releases (ver `data_manager.py`).
"""

from __future__ import annotations

import json
import os
from collections.abc import Sequence
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
from .resolve import NameQuery, resolve_municipio_names

JoinStrategy = Literal["inner", "left", "right", "full", "semi", "anti", "cross", "outer"]
_DF_CACHE_MAXSIZE = 8


def _resolve_dataset_name(dataset_name: str | Dataset, published: list[str] | None = None) -> str:
    """Valida contra el enum `Dataset`; si el nombre no está en el enum pero
    SÍ está en el catálogo cargado (`published`), se acepta tal cual.

    Así una versión vieja del paquete puede leer un dataset agregado en un
    bundle más nuevo (compatibilidad hacia adelante — ver README, sección
    "Compatibilidad entre paquete y bundle"), sin perder la sugerencia de
    typo del enum cuando el nombre no existe en ninguna parte."""
    if isinstance(dataset_name, Dataset):
        return dataset_name.value
    try:
        return Dataset.from_string(dataset_name).value
    except ValueError as exc:
        if published is not None and dataset_name in published:
            return dataset_name
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
        elif os.environ.get(data_manager.DATA_DIR_ENV):
            resolved_catalog = Path(os.environ[data_manager.DATA_DIR_ENV]) / "dataset_catalog.json"
        else:
            dev_catalog = _find_dev_catalog()
            if dev_catalog is not None:
                resolved_catalog = dev_catalog
            else:
                if not auto_update:
                    raise ColombiaOpenDatasetError(
                        "No se encontró data/normalized/dataset_catalog.json y "
                        "auto_update=False. Pasa data_dir/catalog_path, define "
                        f"{data_manager.DATA_DIR_ENV}, o corre `make build` en un "
                        "checkout del repo."
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
        name = _resolve_dataset_name(dataset_name, self.list_datasets())
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
        name = _resolve_dataset_name(dataset_name, self.list_datasets())
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
        name = _resolve_dataset_name(dataset_name, self.list_datasets())
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

    def resolve_municipios(
        self,
        names: Sequence[NameQuery],
        *,
        departamento: str | None = None,
    ) -> pl.DataFrame:
        """Resuelve nombres de municipio a código DIVIPOLA.

        Coincidencia exacta normalizada (sin tildes, minúsculas), luego una
        tabla de alias curada ("Cali", "Bogotá", "Cartagena", "Cúcuta"…).
        Si un nombre existe en varios departamentos (Rionegro, La Unión…)
        y no se indica cuál, NO se escoge uno: `matched=False`,
        `match_type="ambiguous"` y los candidatos en `candidates`.

        Desambigua con `departamento="Antioquia"` (o `"05"`) para todos, o
        por nombre con tuplas: `[("Rionegro", "Antioquia"), "Cali"]`.

        Columnas: query, departamento, matched, match_type
        (exact|alias|ambiguous|not_found), cod_mpio, nombre_mpio, cod_dpto,
        candidates (candidatos si es ambiguo; sugerencias aproximadas si no
        se encontró — nunca se usan como match automático).
        """
        municipios = self.load_polars("municipios")
        if "nombre_dpto" not in municipios.columns and "departamentos" in self.list_datasets():
            departamentos = self.load_polars("departamentos").select("cod_dpto", "nombre_dpto")
            municipios = municipios.join(departamentos, on="cod_dpto", how="left")
        return resolve_municipio_names(municipios, names, departamento=departamento)

    def summary(self) -> dict[str, Any]:
        return {
            "datasets": len(self.catalog.get("datasets", [])),
            "generated_at_utc": self.catalog.get("generated_at_utc"),
            "names": self.list_datasets(),
        }
