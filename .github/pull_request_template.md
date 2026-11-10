<!--
Título de la PR en formato Conventional Commits (lo valida el CI):
  feat: agregar <dataset> (<entidad>)  ·  fix: ...  ·  docs: ...
Ver .github/CONTRIBUTING.md
-->

## Qué cambia y por qué

Closes #

## Tipo de cambio

- [ ] Fuente / dataset nuevo
- [ ] Fix en extractor / validador / builder existente
- [ ] Librería pública / API / CLI / MCP
- [ ] Docs / landing page
- [ ] CI / tooling

## Checklist general

- [ ] `make check` pasa en local
- [ ] `make doctor` pasa en local
- [ ] Tests nuevos o actualizados cubren el cambio
- [ ] Si rompe compatibilidad (columna publicada, método público), el título lleva `!`

## Si agrega o modifica una fuente

- [ ] Verifiqué el endpoint/URL actual con `curl` (no solo búsqueda web)
- [ ] Revisé la licencia y actualicé `docs/licenses/data_licenses.md`
- [ ] Extractor con fallback marcado `source_mode="fallback"` — nunca datos fabricados
- [ ] `cod_dpto` / `cod_mpio` como string de ancho fijo (2 / 5)
- [ ] Validador registrado en `src/validation/__init__.py::VALIDATORS`
- [ ] `source_url` y `source_name` presentes en el catálogo
- [ ] Todas las columnas documentadas en `docs/datasets/{name}.md`
- [ ] Fila marcada en `docs/roadmap/roadmap.md`
- [ ] Dataset agregado al enum `src/colombia_open/datasets.py::Dataset`
- [ ] (Opcional, PR aparte) Título/grupo en `content/catalogo.json` y fila ligada en `content/roadmap.json` del repo [colombia-open.github.io](https://github.com/colombia-open/colombia-open.github.io) — la landing ya muestra el dataset sin esto, solo decide cómo se presenta

## ¿Usaste un agente de IA?

- [ ] Sí — revisé y entiendo todo el diff
- [ ] No
