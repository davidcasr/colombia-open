"""Constantes compartidas de validación (umbrales, conteos esperados, bboxes)."""

# Bounding box aproximado del territorio continental + insular de Colombia.
# Usado para detectar centroides corruptos/fuera de rango, no para precisión
# geográfica.
COLOMBIA_LON_MIN = -82.0  # incluye San Andrés y Providencia
COLOMBIA_LON_MAX = -66.8
COLOMBIA_LAT_MIN = -4.3
COLOMBIA_LAT_MAX = 13.5

EXPECTED_DEPARTAMENTOS_COUNT = 33
EXPECTED_MUNICIPIOS_MIN_COUNT = 1100

# Proyecciones de población municipal (demografía): mismo umbral generoso
# que usa el extractor (EXPECTED_MIN_ROWS) para detectar truncamiento
# severo sin reventar por variaciones normales año a año.
EXPECTED_DEMOGRAFIA_MIN_COUNT = 70_000
DEMOGRAFIA_AREA_GEOGRAFICA_VALUES = {
    "Cabecera Municipal",
    "Centros Poblados y Rural Disperso",
    "Total",
}

# Directorio de establecimientos educativos (MEN).
EXPECTED_EDUCACION_ESTABLECIMIENTOS_MIN_COUNT = 500_000
# Bajo este umbral de (valores distintos de codigo_dane / filas) para un
# año dado, se trata como un defecto conocido de la fuente para ese año
# (warning), no como clave primaria duplicada (error) — ver nota en
# src/extractors/educacion_establecimientos_extractor.py sobre el año 2023.
EDUCACION_CODIGO_DANE_LOW_CARDINALITY_RATIO = 0.5

# Hurto a personas (MinDefensa / Policía). Mismo umbral que usa el extractor
# (EXPECTED_MIN_ROWS): 651200 filas en vivo el 2026-10-19, menos ~365
# excluidas por "SIN ESTABLECER".
EXPECTED_DELINCUENCIA_HURTO_PERSONAS_MIN_COUNT = 600_000
# 1377323 filas tras agregar centro poblado -> municipio (2026-10-19).
EXPECTED_DELINCUENCIA_LESIONES_PERSONALES_MIN_COUNT = 1_300_000
# Un año con menos municipios distintos que esta fracción de la mediana
# entre años se reporta como posible falta de desagregación municipal en la
# fuente (warning) — ver nota sobre 2008 en
# src/extractors/delincuencia_hurto_personas_extractor.py.
DELINCUENCIA_LOW_MPIO_COVERAGE_RATIO = 0.5
# 397361 filas tras agregar centro poblado -> municipio (confirmado en vivo
# 2026-10-20, de 653384 filas crudas con cantidad siempre "1").
EXPECTED_DELINCUENCIA_HURTO_MODALIDADES_MIN_COUNT = 350_000
