"""CLI de colombia-open. Los comandos son agnósticos al dataset: agregar una
fuente nueva no requiere código nuevo aquí, solo una entrada en el registro
y en el catálogo generado."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable

from . import __version__
from .core import ColombiaOpen
from .exceptions import ColombiaOpenDataError, ColombiaOpenError


def _cmd_version(_args: argparse.Namespace) -> int:
    print(f"colombia-open {__version__}")
    return 0


def _cmd_list(_args: argparse.Namespace) -> int:
    hub = ColombiaOpen()
    for name in hub.list_datasets():
        print(name)
    return 0


def _cmd_show(args: argparse.Namespace) -> int:
    hub = ColombiaOpen()
    entry = hub.get_dataset(args.dataset)
    for key, value in entry.items():
        print(f"{key}: {value}")
    return 0


def _cmd_path(args: argparse.Namespace) -> int:
    hub = ColombiaOpen()
    print(hub.get_output_path(args.dataset, args.output))
    return 0


def _cmd_example(args: argparse.Namespace) -> int:
    hub = ColombiaOpen()
    entry = hub.get_dataset(args.dataset)
    examples = entry.get("usage_examples", {})
    if args.kind not in examples:
        print(f"No hay ejemplo '{args.kind}' para '{args.dataset}'.", file=sys.stderr)
        return 1
    print(examples[args.kind])
    return 0


def _cmd_validate(args: argparse.Namespace) -> int:
    hub = ColombiaOpen()
    result = hub.validate_dataset(args.dataset)
    print(f"status: {result['status']}  record_count: {result['record_count']}")
    for error in result.get("errors", []):
        print(f"  error: {error}")
    for warning in result.get("warnings", []):
        print(f"  warning: {warning}")
    return 1 if result["status"] == "error" else 0


def _cmd_summary(_args: argparse.Namespace) -> int:
    hub = ColombiaOpen()
    for key, value in hub.summary().items():
        print(f"{key}: {value}")
    return 0


def _cmd_mcp(_args: argparse.Namespace) -> int:
    try:
        from . import mcp_server
    except ModuleNotFoundError as exc:
        raise ColombiaOpenDataError(
            "El comando 'mcp' necesita el extra 'mcp': `pip install colombia-open[mcp]`"
        ) from exc

    mcp_server.main()
    return 0


def _cmd_cache(args: argparse.Namespace) -> int:
    from . import data_manager

    if args.action == "status":
        for key, value in data_manager.cache_status().items():
            print(f"{key}: {value}")
    elif args.action == "clear":
        data_manager.clear_cache()
        print("Caché eliminado.")
    elif args.action == "update":
        path = data_manager.download_and_cache_bundle(force=True)
        print(f"Bundle actualizado en: {path}")
    return 0


HANDLERS: dict[str, Callable[[argparse.Namespace], int]] = {
    "version": _cmd_version,
    "list": _cmd_list,
    "show": _cmd_show,
    "path": _cmd_path,
    "example": _cmd_example,
    "validate": _cmd_validate,
    "summary": _cmd_summary,
    "cache": _cmd_cache,
    "mcp": _cmd_mcp,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="colombia-open")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("version", help="Mostrar la versión instalada")
    subparsers.add_parser("list", help="Listar datasets disponibles")
    subparsers.add_parser("summary", help="Resumen del catálogo")

    show_parser = subparsers.add_parser("show", help="Mostrar metadata de un dataset")
    show_parser.add_argument("dataset")

    path_parser = subparsers.add_parser("path", help="Resolver el path de un output")
    path_parser.add_argument("dataset")
    path_parser.add_argument("--output", default="parquet")

    example_parser = subparsers.add_parser("example", help="Mostrar un ejemplo de uso")
    example_parser.add_argument("dataset")
    example_parser.add_argument("--kind", default="python", choices=["python", "cli"])

    validate_parser = subparsers.add_parser("validate", help="Validar un dataset")
    validate_parser.add_argument("dataset")

    cache_parser = subparsers.add_parser("cache", help="Gestionar el caché local del bundle")
    cache_parser.add_argument("action", choices=["status", "clear", "update"])

    subparsers.add_parser("mcp", help="Levantar el servidor MCP (stdio) — requiere el extra 'mcp'")

    return parser


def _main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    handler = HANDLERS[args.command]
    return handler(args)


def main(argv: list[str] | None = None) -> int:
    try:
        return _main(argv)
    except ColombiaOpenError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
