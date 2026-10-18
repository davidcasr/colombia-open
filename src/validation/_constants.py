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
