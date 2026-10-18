#!/usr/bin/env python
"""Empaqueta data/normalized/ en el bundle que `data_manager.py` descarga.

Genera `colombia-open-bundle.zip` + `colombia-open-bundle.zip.sha256` en la
raíz del repo. Usado por el workflow de Release — no corre en CI normal.
"""

from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
NORMALIZED_DIR = ROOT_DIR / "data" / "normalized"
BUNDLE_PATH = ROOT_DIR / "colombia-open-bundle.zip"
CHECKSUM_PATH = ROOT_DIR / "colombia-open-bundle.zip.sha256"


def main() -> int:
    if not NORMALIZED_DIR.exists():
        print(f"No existe {NORMALIZED_DIR}. Corre `make build` primero.")
        return 1

    with zipfile.ZipFile(BUNDLE_PATH, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(NORMALIZED_DIR.rglob("*")):
            if path.is_file():
                zf.write(path, arcname=path.relative_to(NORMALIZED_DIR))

    digest = hashlib.sha256(BUNDLE_PATH.read_bytes()).hexdigest()
    CHECKSUM_PATH.write_text(f"{digest}  {BUNDLE_PATH.name}\n", encoding="utf-8")

    print(f"Bundle: {BUNDLE_PATH} ({BUNDLE_PATH.stat().st_size} bytes)")
    print(f"SHA256: {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
