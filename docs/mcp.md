# Servidor MCP

`colombia-open` expone su catálogo a agentes de IA vía [MCP](https://modelcontextprotocol.io/)
(Model Context Protocol). El servidor vive en `src/colombia_open/mcp_server.py`
y se levanta con el subcomando `mcp` del CLI existente — no hay un
ejecutable aparte.

## Instalar y correr

```bash
pip install "colombia-open[mcp]"
colombia-open mcp
```

Esto levanta el servidor en transporte **stdio** (el estándar para
servidores MCP locales) y se queda esperando mensajes JSON-RPC — no hace
nada visible por sí solo, lo levanta el cliente MCP.

Config típica de cliente (Claude Desktop, Claude Code, u otro cliente MCP):

```json
{
  "mcpServers": {
    "colombia-open": { "command": "colombia-open", "args": ["mcp"] }
  }
}
```

Si corrés `colombia-open mcp` sin el extra `mcp` instalado, el error es
claro (`necesita el extra 'mcp': pip install colombia-open[mcp]`) — no un
traceback de import.

## Tools

Tres tools, a propósito pocas. SQL compone mejor que muchos parámetros de
filtro angostos, y un agente ya sabe escribir SQL — así que en vez de
exponer un tool por cada operación (filtrar, unir, agregar), hay un solo
`query()` que las cubre todas.

### `list_datasets()`

Sin parámetros. Devuelve, por cada dataset: `dataset`, `description`,
`record_count`, `source_name`, `license`.

### `describe_dataset(dataset: str)`

El catalog entry completo de `ColombiaOpen.get_dataset()` (incluye
`source_url`, `source_mode`, `reuse_policy`, `join_keys`,
`validation_status` y `warnings` — estos últimos ya calculados en build
time, no se re-valida en vivo) **+** una clave `columns` con el esquema
(nombre de columna → tipo), leído del parquet sin cargar filas.

Revisá `join_keys` acá antes de escribir un JOIN en `query()`.

### `query(sql: str, limit: int | None = None)`

Corre una query SQL de **solo lectura** (debe empezar con `SELECT` o
`WITH`) contra todos los datasets, cada uno registrado como una tabla con
su mismo nombre — podés hacer JOIN entre datasets en una sola query:

```sql
SELECT m.nombre_mpio, COUNT(*) AS n
FROM educacion_establecimientos e
JOIN municipios m ON e.cod_mpio = m.cod_mpio
WHERE e.anio = 2024
GROUP BY m.nombre_mpio
ORDER BY n DESC
```

Devuelve `{"rows": [...], "row_count": int, "truncated": bool, "limit": int}`.

**Las filas siempre se limitan** — default 100, máximo 1000 incluso si
`limit` pide más. `truncated=True` significa que hubo más filas de las
devueltas: la respuesta correcta es agregar `WHERE`/`GROUP BY` para acotar
del lado del servidor, no pedir un `limit` más alto. Esto es deliberado:
`educacion_establecimientos` tiene 606,206 filas — un tool que las vuelque
crudas reventaría el contexto de cualquier agente.

## Por qué `query()` valida el SQL antes de ejecutarlo

El motor SQL de polars soporta funciones de tabla con ruta arbitraria —
`read_parquet('/cualquier/archivo')`, `read_csv(...)`, `scan_parquet(...)`,
`glob(...)` — que **ignoran completamente las tablas registradas** y leen
cualquier archivo del disco accesible al proceso del servidor. Confirmado
ejecutando código real contra polars, no es una suposición teórica: un
`query(sql)` que reenviara el string tal cual al motor sería un primitivo
de lectura arbitraria de archivos locales, explotable por un agente (o uno
con prompt injection).

Por eso `query()` rechaza, antes de que el string toque el motor SQL,
cualquier query que:
- No empiece con `SELECT` o `WITH`.
- Mencione cualquier función `read_*` o `scan_*` (`read_csv`,
  `read_parquet`, `read_json`, `read_ndjson`, `read_ipc`, `scan_parquet`…)
  o `glob` — por **nombre**, con o sin paréntesis pegado. Una versión
  anterior buscaba el substring `read_csv(` y se saltaba con
  `read_csv ('/etc/passwd')`, un comentario o un salto de línea antes del
  paréntesis (y no cubría `read_json`); ver la regresión
  `test_query_impl_rejects_arbitrary_file_read_end_to_end`.
- Contenga comentarios SQL (`--`, `/*`, `*/`).
- Contenga `attach`, `copy`, `pragma`, `insert `, `update `, `delete `, `create `,
  `drop `, o un `;` que no sea solo el final del string (un `;` final
  inofensivo, hábito común al escribir SQL, se tolera).
- Exceda 10,000 caracteres.

No hace falta validar "a mano" que las tablas referenidas en el `FROM`
sean datasets reales — el `SQLContext` solo tiene registrados los
datasets del catálogo, así que referenciar cualquier otra cosa falla
naturalmente con un error de "tabla no encontrada" del propio motor.

### Límites conocidos

El motor es **polars** (`pl.SQLContext`), no DuckDB: no tiene `httpfs`,
`INSTALL`/`LOAD` de extensiones ni `enable_external_access`, así que esas
superficies no aplican — la única vía de E/S son las funciones de tabla de
arriba. Lo que polars **no** ofrece es timeout por consulta ni límite de
memoria: una query costosa (p. ej. un `CROSS JOIN` entre datasets grandes)
puede tardar o consumir mucha RAM aunque la salida se recorte a `limit`.
Si expones el servidor a agentes no confiables, córrelo en un proceso con
límites del sistema operativo (contenedor, `ulimit`/cgroups).

Ver los tests de regresión de esto en `tests/test_mcp_server.py`
(`test_query_impl_rejects_unsafe_sql`) — no son opcionales, son la prueba
de este hallazgo.

## Qué NO se expone, y por qué

- **`cross_view()`** — subsumido por `JOIN` en `query()`.
- **`resolve_municipios()`** — una vez el agente ve `nombre_mpio_clean` vía
  `describe_dataset("municipios")`, es trivial expresarlo como
  `WHERE nombre_mpio_clean = 'medellin'`. Ojo: el agente debe filtrar
  también por `cod_dpto` ante nombres repetidos (Rionegro, La Unión…) — la
  tabla de alias curada de la librería (`resolve.py`) no está expuesta.
- **`validate_dataset()`** — es pipeline-only (importa `src.registry`/
  `src.validation`, que requieren el extra `pipeline`); exponerlo violaría
  que el extra `mcp` se mantenga liviano. Los `warnings`/`validation_status`
  ya calculados en build time, surfaceados por `describe_dataset()`, cubren
  el caso de uso de "¿puedo confiar en este dato?" sin necesitar re-validar
  en vivo.

## Limitaciones conocidas

- Un dataset listado en `list_datasets()` siempre existe en el enum
  `Dataset` de la librería — el catálogo y el enum deben estar en sync
  (ya lo están por diseño: cada fuente nueva actualiza ambos, ver
  `CLAUDE.md`).
- `query()` construye un `pl.SQLContext` nuevo en cada llamada (nunca lo
  reusa entre llamadas) — correcto para aislamiento, pero significa que no
  hay estado de sesión SQL entre tools calls (cada `query()` es
  independiente, no podés definir una tabla temporal en una llamada y
  usarla en la siguiente).
- El transporte es solo **stdio** por ahora — no hay modo HTTP/SSE para
  correr el servidor como un proceso remoto compartido.
