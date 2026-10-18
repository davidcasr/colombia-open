#!/usr/bin/env python
"""Verifica el catálogo generado (`data/normalized/dataset_catalog.json`):
todos los datasets deben estar en status "ok". Con `--require-live`, además
rechaza cualquier dataset en `source_mode="fallback"` — ese es el gate que
usa CI antes de publicar (ver `.github/workflows/pipeline-check.yml`).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
CATALOG_PATH = ROOT_DIR / "data" / "normalized" / "dataset_catalog.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--require-live",
        action="store_true",
        help="Rechaza cualquier dataset con source_mode=fallback (gate de publicación)",
    )
    args = parser.parse_args()

    if not CATALOG_PATH.exists():
        print(f"No existe {CATALOG_PATH}. Corre `make build` primero.", file=sys.stderr)
        return 1

    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    datasets = catalog.get("datasets", [])
    if not datasets:
        print("El catálogo no tiene datasets.", file=sys.stderr)
        return 1

    had_errors = False
    for entry in datasets:
        name = entry["dataset"]
        status = entry.get("validation_status")
        source_mode = entry.get("source_mode")
        if status != "ok":
            print(f"[ERROR] {name}: validation_status={status}")
            had_errors = True
        elif args.require_live and source_mode != "live":
            print(f"[ERROR] {name}: source_mode={source_mode}, se requiere 'live' para publicar")
            had_errors = True
        else:
            print(f"[OK] {name}: status=ok source_mode={source_mode}")

    return 1 if had_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
