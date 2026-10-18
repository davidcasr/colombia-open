#!/usr/bin/env python
"""Gate anti-drift: todo dataset del registro debe tener un validador
registrado en `src.validation.VALIDATORS`. Un validador sin registrar se
salta silenciosamente en el build — este check lo convierte en un error
explícito. Ver `.claude/rules/validation.md`.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.registry import load_registry  # noqa: E402
from src.validation import VALIDATORS  # noqa: E402


def main() -> int:
    registry = load_registry()
    missing = [name for name in registry if name not in VALIDATORS]
    if missing:
        print("Datasets sin validador registrado en src.validation.VALIDATORS:")
        for name in missing:
            print(f"  - {name}")
        return 1
    print(f"OK: {len(registry)} datasets, todos con validador registrado.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
