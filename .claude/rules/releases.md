# Convención de versionado y releases

`colombia-open` publica dos cosas por separado, cada una con su propio
workflow manual:

- **Datos**: GitHub Releases con el bundle de `data/normalized/` + SHA256
  (`.github/workflows/release.yml`). Es lo que `ColombiaOpen()` descarga y
  cachea automáticamente en el primer uso (ver `data_manager.py`).
- **Paquete**: el código de `colombia_open/` a PyPI, vía trusted
  publishing — sin token almacenado (`.github/workflows/publish.yml`).
  Verificado end-to-end el 2026-10-18 (build local + venv aislado +
  descarga real del bundle), pero **todavía no se ha corrido el primer
  publish real** — requiere que el mantenedor configure un trusted
  publisher en pypi.org primero (ver el comentario del workflow).

Usa SemVer (`MAJOR.MINOR.PATCH`) sobre `version` en `pyproject.toml` para
ambos — el mismo número de versión identifica el release de datos
(`vX.Y.Z` en GitHub Releases) y el release del paquete (`X.Y.Z` en PyPI).

## Qué sube cada número

**PATCH** (`0.X.Y` → `0.X.(Y+1)`)
- Fix en un extractor/validador existente que no cambia el esquema
  publicado ni agrega un dataset.
- Corrección de docs, typos, CI/pipeline sin impacto en los datos
  publicados.
- Actualización de dependencias sin cambio de comportamiento.

**MINOR** (`0.X.Y` → `0.(X+1).0`)
- Agregar una fuente/dataset nuevo al catálogo — el caso más común en
  este proyecto, dado el ritmo "una fuente por fin de semana" (ver
  `CLAUDE.md`).
- Agregar un método nuevo a la API pública (`ColombiaOpen`) de forma
  retrocompatible.

**MAJOR** (`X.Y.Z` → `(X+1).0.0`)
- Cambio de esquema que rompe compatibilidad en un dataset ya publicado
  (renombrar/quitar una columna, cambiar su tipo).
- Cambio breaking en la API pública (renombrar/quitar un método, cambiar
  una firma de forma incompatible).
- Mientras el proyecto esté en `0.x`, el salto real a `1.0.0` queda
  reservado para cuando el catálogo y la API se consideren estables — no
  es solo "un cambio grande", es ese hito específico.

## Reglas al cortar un release

1. **Confirma cuál fue el último release REAL antes de asumir el
   siguiente número** — `pyproject.toml` puede estar desactualizado si
   alguien olvidó bumpearlo. Nunca asumas el estado de releases solo por
   lo que dice el código:

   ```bash
   gh release list
   git fetch --tags && git tag --sort=-v:refname
   ```

2. El número de versión en `pyproject.toml` se bumpea **como parte del
   commit que cierra el trabajo que se va a liberar** — nunca se
   "adelanta" especulativamente antes de que el trabajo esté listo, ni se
   reusa un número que ya corresponde a un tag publicado.

3. El tag del release **siempre coincide exactamente** con `version` en
   `pyproject.toml` en el commit que se está liberando (ej. si
   `pyproject.toml` dice `0.2.0`, el tag es `v0.2.0`).

4. Cortar el release (manual a propósito — ver el comentario en
   `.github/workflows/release.yml`, es decisión del mantenedor, no algo
   que un agente dispare sin que se le pida explícitamente):

   ```bash
   gh workflow run release.yml -f tag=vX.Y.Z
   gh run watch
   ```

   El workflow reconstruye desde las fuentes en vivo y **falla el release
   si cualquier dataset queda en `source_mode="fallback"`**
   (`scripts/verify_pipeline.py --require-live`) — eso es intencional, no
   un bug a silenciar.

5. Después de un release exitoso, revisa que no haya quedado
   documentación desactualizada referenciando el tag anterior (README
   "Estado del proyecto", landing page, etc.) — ver el incidente real de
   esto en el historial de commits de 2026-10-18, donde el README quedó
   mencionando `v0.1.0` después de publicarse `v0.2.0`.

## Publicar el paquete a PyPI

Decisión del mantenedor, no algo que un agente dispare sin que se le pida
explícitamente (mismo criterio que el release de datos). Requiere que el
trusted publisher ya esté configurado en pypi.org (ver el comentario de
`publish.yml`) — sin eso, el paso de publicación falla con un error de
autenticación, no hay ningún secret que configurar en este repo.

```bash
gh workflow run publish.yml -f expected_version=X.Y.Z
gh run watch
```

El workflow valida que `pyproject.toml` tenga exactamente esa versión
antes de construir y publicar — falla fuerte si no coincide, en vez de
publicar silenciosamente la versión equivocada.
