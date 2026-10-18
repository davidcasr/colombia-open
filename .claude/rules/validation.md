---
description: Qué significa "validado" para un dataset en colombia-open
appliesTo: "src/validation/**"
---

# Contrato de validación

## Qué "validado" significa aquí

Un dataset está validado cuando su función `validate_{dataset}()` devuelve
`status: "ok"` — eso significa, como mínimo:

1. **No está vacío.**
2. **La clave primaria es única** (`cod_mpio` en municipios, `cod_dpto` en
   departamentos) — usa `_helpers.duplicate_count()`.
3. **Los códigos administrativos tienen el ancho fijo correcto**
   (`_helpers.invalid_fixed_length_count()`) — 2 dígitos para
   departamento, 5 para municipio. Esto detecta el bug clásico de "Excel/
   pandas se comió el cero inicial" antes de que llegue a producción.
4. **Integridad referencial** donde aplique (`_helpers.unknown_codes_count()`)
   — ej. todo `cod_dpto` en `municipios` debe existir en `departamentos`.
5. **Si `source_mode == "live"`**: el conteo de filas no puede ser
   sospechosamente bajo (`EXPECTED_*_MIN_COUNT` en `_constants.py`) — una
   fuente que de repente devuelve 10 filas en vez de 1100 es una fuente
   rota, no un dataset pequeño.

## Forma del resultado — nunca lanza, y está tipado

```python
from .result import ValidationResult

def validate_X(df: pl.DataFrame, metadata: dict | None = None) -> ValidationResult:
    return ValidationResult(
        dataset="X",
        status="error" if errors else "ok",
        record_count=df.height,
        errors=[...],    # lista de strings — problemas que bloquean publicación
        warnings=[...],  # lista de strings — no bloquean, pero se reportan
    )
```

`ValidationResult` (`src/validation/result.py`) es un `dataclass` frozen,
no un `dict[str, Any]` — así mypy chequea de verdad los campos (`.status`,
`.errors`, `.warnings`) en vez de aceptar cualquier llave. Tiene un método
`.to_dict()` solo para la frontera pública (`colombia_open.core.
ColombiaOpen.validate_dataset()` lo usa para mantener su firma pública
`dict[str, Any]`) — el código interno del pipeline siempre usa el objeto
tipado, nunca el dict.

Un validador **nunca lanza una excepción por un problema de calidad de
datos** — siempre devuelve un `ValidationResult`. Quien llama
(`build_pipeline.py`, `scripts/verify_pipeline.py`, el CLI `colombia-open
validate`) decide si `status == "error"` debe detener el build. Esto
mantiene a los validadores como funciones puras, fáciles de testear con un
DataFrame construido a mano (accede a los campos por atributo:
`result.status`, `result.errors`) — ver
`tests/validation/test_territorio.py` como plantilla.

## Dónde vive cada pieza

- Un módulo por dominio bajo `src/validation/_{dominio}.py` (ej.
  `_territorio.py` para departamentos/municipios). Nunca valides inline en
  `build_pipeline.py` — siempre en su propio módulo.
- Primitivas compartidas en `_helpers.py` (no dupliques
  `duplicate_count`/`missing_columns`/etc. dentro de un módulo de dominio).
- Constantes específicas del dominio (bounding box, conteos esperados) en
  `_constants.py`.
- **Registro obligatorio**: toda función `validate_*` se exporta en
  `src/validation/__init__.py` y se agrega al dict `VALIDATORS`.
  `scripts/check_validation_registration.py` (parte de `make doctor`)
  falla si un dataset del registro no tiene validador registrado — un
  validador que exists pero no está en `VALIDATORS` se salta en silencio
  en el build, así que esto NO es opcional.

## Warnings esperados vs. errores

- `source_mode == "fallback"` siempre agrega un **warning**, nunca un
  error — el fallback es válido para desarrollo, solo no se publica (eso
  lo decide `scripts/verify_pipeline.py --require-live`, no el validador).
- Coordenadas fuera del bounding box de Colombia (`_constants.py`) son
  **warning**, no error — podría ser un dato legítimo mal registrado en la
  fuente que vale la pena investigar, pero no amerita bloquear el build
  por sí solo.
- Duplicados de clave primaria, ancho de código incorrecto, y filas
  huérfanas por integridad referencial son siempre **error**.

## Tests de un validador nuevo

Como mínimo (ver `tests/validation/test_territorio.py`):
- Caso feliz: DataFrame válido → `status == "ok"`.
- Un caso por cada regla de error (duplicado, ancho de código, huérfano).
- DataFrame vacío / columnas faltantes → error claro, no un traceback.
- `source_mode == "fallback"` → warning presente.
