"""Servidor MCP: expone el catálogo de colombia-open a agentes de IA.

Tres tools, deliberadamente pocas — SQL compone mejor que muchos parámetros
de filtro angostos, y un agente ya sabe escribir SQL:

- `list_datasets()`: qué datasets existen.
- `describe_dataset(dataset)`: metadata + esquema de columnas.
- `query(sql, limit=None)`: SQL de solo lectura contra todos los datasets
  como tablas nombradas (permite JOIN entre datasets en una sola query).

No se exponen `cross_view()` (subsumido por JOIN en `query`),
`resolve_municipios()` (trivial una vez el agente ve `nombre_mpio_clean`
vía `describe_dataset`) ni `validate_dataset()` (pipeline-only — importaría
`src.registry`/`src.validation`, lo que violaría que el extra `mcp` se
mantenga liviano; los `warnings`/`validation_status` ya calculados en el
catálogo, surfaceados por `describe_dataset`, cubren el caso de uso).

## Por qué `query()` valida el SQL antes de ejecutarlo

El dialecto SQL de polars soporta funciones de tabla con ruta arbitraria —
`read_parquet('/cualquier/archivo')`, `read_csv(...)`, `scan_parquet(...)`,
`glob(...)` — que ignoran completamente las tablas registradas en el
`SQLContext` y leen cualquier archivo del disco accesible al proceso.
Confirmado ejecutando código real contra polars (no es una suposición): un
`query(sql)` que reenvíe el string tal cual a `SQLContext.execute()` es un
primitivo de lectura arbitraria de archivos locales. `_validate_sql()`
rechaza esto con una lista de bloqueo ANTES de que el string toque el motor
SQL — ver tests de regresión en `tests/test_mcp_server.py`.

Se invoca siempre como módulo, nunca como script suelto — en la práctica
vía `colombia-open mcp` (ver `cli.py`), que es lo que un cliente MCP
configura como comando.
"""

from __future__ import annotations

from typing import Any

import polars as pl
from mcp.server.fastmcp import FastMCP

from .core import ColombiaOpen
from .exceptions import ColombiaOpenError

DEFAULT_LIMIT = 100
MAX_LIMIT = 1000
_MAX_SQL_LENGTH = 10_000

# Funciones/keywords que permiten leer archivos fuera de las tablas
# registradas, o mutar/ejecutar más de una sentencia. Búsqueda de substring
# case-insensitive sobre el string completo — no requiere parsear SQL
# estructuralmente: un token prohibido se detecta sin importar en qué nivel
# de anidamiento, UNION o subquery aparezca.
_FORBIDDEN_SQL_TOKENS = (
    "read_csv(",
    "read_parquet(",
    "read_ndjson(",
    "read_ipc(",
    "scan_csv(",
    "scan_parquet(",
    "scan_ndjson(",
    "scan_ipc(",
    "glob(",
    "attach",
    "copy",
    "pragma",
    "insert ",
    "update ",
    "delete ",
    "create ",
    "drop ",
    ";",
)


class McpQueryError(Exception):
    """SQL rechazado por `_validate_sql()` — nunca llega a `SQLContext`."""


def _clean_sql(sql: str) -> str:
    """Pela espacios y UN ';' final inofensivo (hábito común al escribir
    SQL) — no afecta la detección de inyección real, que es sobre ';' que
    queden en medio del string después de esto."""
    if len(sql) > _MAX_SQL_LENGTH:
        raise McpQueryError(f"La query excede el máximo de {_MAX_SQL_LENGTH} caracteres.")
    return sql.strip().rstrip(";").strip()


def _validate_sql(cleaned_sql: str) -> None:
    if not cleaned_sql:
        raise McpQueryError("La query está vacía.")
    lowered = cleaned_sql.lower()
    if not (lowered.startswith("select") or lowered.startswith("with")):
        raise McpQueryError("Solo se permiten queries que empiecen con SELECT o WITH.")
    for token in _FORBIDDEN_SQL_TOKENS:
        if token in lowered:
            raise McpQueryError(
                f"Query rechazada: contiene '{token.strip()}', no permitido. "
                "Solo se puede leer de los datasets registrados (ver list_datasets())."
            )


def _build_sql_context(hub: ColombiaOpen) -> pl.SQLContext[pl.LazyFrame]:
    # Fresco en cada llamada, nunca cacheado: un SQLContext expone DDL
    # (DROP TABLE, etc.) que solo afecta su propio registro de tablas en
    # memoria, no los datos en disco — pero no hay razón para compartir
    # estado entre queries.
    tables = {name: pl.scan_parquet(hub.get_output_path(name)) for name in hub.list_datasets()}
    return pl.SQLContext(tables, eager=False)


def _jsonify(df: pl.DataFrame) -> list[dict[str, Any]]:
    # Date/Datetime/Duration/Time no son JSON-serializables por defecto —
    # castear a string antes de to_dicts() en vez de confiar en que el
    # serializador del SDK lo maneje.
    cast_exprs = [
        pl.col(name).cast(pl.Utf8)
        for name, dtype in df.schema.items()
        if dtype.base_type() in (pl.Date, pl.Datetime, pl.Duration, pl.Time)
    ]
    if cast_exprs:
        df = df.with_columns(cast_exprs)
    return df.to_dicts()


def _list_datasets_impl(hub: ColombiaOpen) -> list[dict[str, Any]]:
    results = []
    for name in hub.list_datasets():
        entry = hub.get_dataset(name)
        reuse_policy = entry.get("reuse_policy") or {}
        results.append(
            {
                "dataset": name,
                "description": entry.get("description"),
                "record_count": entry.get("record_count"),
                "source_name": entry.get("source_name"),
                "license": reuse_policy.get("license"),
            }
        )
    return results


def _describe_dataset_impl(hub: ColombiaOpen, dataset: str) -> dict[str, Any]:
    entry = dict(hub.get_dataset(dataset))
    schema = pl.read_parquet_schema(hub.get_output_path(dataset))
    entry["columns"] = {name: str(dtype) for name, dtype in schema.items()}
    return entry


def _query_impl(hub: ColombiaOpen, sql: str, limit: int | None = None) -> dict[str, Any]:
    cleaned = _clean_sql(sql)
    _validate_sql(cleaned)
    effective_limit = min(limit, MAX_LIMIT) if limit else DEFAULT_LIMIT
    effective_limit = max(1, min(effective_limit, MAX_LIMIT))

    ctx = _build_sql_context(hub)
    # nosec B608 — bandit marca cualquier SQL armado con f-string como
    # posible inyección, pero `cleaned` ya pasó por `_validate_sql()`
    # (denylist de funciones de lectura de archivo/DDL/DML/multi-statement)
    # arriba. Este wrap es exactamente la funcionalidad del tool, no un bug:
    # `query()` existe para ejecutar SQL del agente, ya acotado por la
    # validación — ver docs/mcp.md sección "Por qué query() valida el SQL".
    wrapped = f"SELECT * FROM ({cleaned}) AS _colombia_open_q LIMIT {effective_limit + 1}"  # nosec B608
    df = ctx.execute(wrapped, eager=True)

    truncated = df.height > effective_limit
    if truncated:
        df = df.head(effective_limit)

    return {
        "rows": _jsonify(df),
        "row_count": df.height,
        "truncated": truncated,
        "limit": effective_limit,
    }


def build_server(hub: ColombiaOpen | None = None) -> FastMCP:
    hub = hub or ColombiaOpen()
    mcp = FastMCP(
        name="colombia-open",
        instructions=(
            "Catálogo de datasets públicos de Colombia, curados y validados. "
            "Usa list_datasets() para ver qué hay, describe_dataset() para ver "
            "esquema/columnas/licencia/warnings de uno, y query() para "
            "filtrar/agregar/unir datasets vía SQL de solo lectura (las "
            "filas se limitan automáticamente, nunca se devuelve un dataset "
            "completo crudo)."
        ),
    )

    @mcp.tool()
    def list_datasets() -> list[dict[str, Any]] | dict[str, str]:
        """Lista los datasets disponibles con una descripción corta, conteo
        de filas, fuente y licencia de cada uno."""
        try:
            return _list_datasets_impl(hub)
        except ColombiaOpenError as exc:
            return {"error": str(exc)}

    @mcp.tool()
    def describe_dataset(dataset: str) -> dict[str, Any]:
        """Metadata completa de un dataset: fuente, licencia, join_keys,
        warnings de calidad de datos conocidos, y el esquema (columna ->
        tipo). Revisa `join_keys` antes de escribir un JOIN en query()."""
        try:
            return _describe_dataset_impl(hub, dataset)
        except ColombiaOpenError as exc:
            return {"error": str(exc)}

    @mcp.tool()
    def query(sql: str, limit: int | None = None) -> dict[str, Any]:
        """Corre una query SQL de solo lectura (SELECT/WITH) contra los
        datasets, cada uno registrado como una tabla con su mismo nombre
        (ver list_datasets() para los nombres exactos). Soporta JOIN entre
        datasets en una sola query. Las filas devueltas siempre se limitan
        (default 100, máximo 1000 incluso si pedís más) — revisa
        `truncated` en la respuesta para saber si hubo más filas de las
        devueltas; en ese caso agregá WHERE/GROUP BY para acotar en vez de
        pedir un limit más alto."""
        try:
            return _query_impl(hub, sql, limit)
        except (ColombiaOpenError, McpQueryError) as exc:
            return {"error": str(exc)}

    return mcp


def main() -> None:
    build_server().run(transport="stdio")


if __name__ == "__main__":
    main()
