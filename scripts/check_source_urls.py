#!/usr/bin/env python
"""Chequeo periódico de liveness de las URLs de fuentes registradas.

Nunca bloquea publicación por sí solo (ver workflow semanal) — un 4xx puede
ser bloqueo anti-bot, no caída real. Solo reporta.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

import requests  # noqa: E402

from src.registry import load_registry  # noqa: E402

SOURCE_URLS = {
    "divipola": "https://www.datos.gov.co/resource/gdxc-w37w.json?$limit=1",
}


def main() -> int:
    registry = load_registry()
    print(f"{len(registry)} datasets en el registro.")

    had_hard_failure = False
    for source_name, url in SOURCE_URLS.items():
        try:
            response = requests.get(url, timeout=30)
            print(f"[{response.status_code}] {source_name}: {url}")
        except requests.RequestException as exc:
            print(f"[ERROR DE RED] {source_name}: {url} -> {exc}")
            had_hard_failure = True

    return 1 if had_hard_failure else 0


if __name__ == "__main__":
    raise SystemExit(main())
