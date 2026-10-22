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
# Geometría de polígonos municipales (MGN vía HDX): mismo umbral que
# municipios, es prácticamente la misma población de filas (1122 vs. 1122
# confirmado en vivo 2026-10-20, 1 discrepancia de código en cada sentido).
EXPECTED_MUNICIPIOS_GEOMETRIA_MIN_COUNT = 1100
GEOM_TYPES_VALIDOS = {"Polygon", "MultiPolygon"}

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
# Saber 11 (ICFES), agregado por (codigo_dane_establecimiento, periodo).
# 105110 filas confirmadas en vivo (2026-10-21), de 7109704 de microdato.
EXPECTED_EDUCACION_SABER11_MIN_COUNT = 90_000

# TRM (Superintendencia Financiera). 8372 filas confirmadas en vivo
# (2026-10-22), serie diaria desde 1991-12-02.
EXPECTED_MACROECONOMIA_TRM_MIN_COUNT = 8_000

# Calidad del aire (IDEAM), filtrado a los 6 contaminantes del Índice de
# Calidad del Aire (ICA) colombiano. ~15600 filas de microdato en la
# fuente (de 30665 totales; el resto son variables meteorológicas y
# PST/NO, fuera de alcance — ver el extractor), colapsadas a ~8985 tras
# deduplicar la fila publicada dos veces (ver docstring del extractor).
CONTAMINANTES_ICA_VALIDOS = {"PM10", "PM2.5", "SO2", "O3", "NO2", "CO"}
EXPECTED_CALIDAD_AIRE_MIN_COUNT = 8_000
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

# Infraestructura / puntos de interés (OpenStreetMap vía Geofabrik). 58046
# filas confirmadas en vivo (2026-10-20), tras geocodificar y excluir ~450
# POI fuera de cualquier polígono de municipios_geometria.
EXPECTED_INFRAESTRUCTURA_POI_MIN_COUNT = 50_000
# Categorías cívicas curadas — ver
# src/extractors/infraestructura_poi_extractor.py (_CATEGORIAS_AMENITY /
# _CATEGORIAS_SHOP). Una categoría fuera de esta lista es un bug de
# clasificación en el extractor, no un dato legítimo nuevo.
CATEGORIAS_POI_VALIDAS = {
    "salud",
    "educacion",
    "seguridad",
    "finanzas",
    "religion",
    "gobierno",
    "transporte",
    "comercio",
}

# Un año con menos municipios distintos que esta fracción de la mediana
# entre años se reporta como posible falta de desagregación municipal en la
# fuente (warning) — ver nota sobre 2008 en
# src/extractors/delincuencia_hurto_personas_extractor.py.
DELINCUENCIA_LOW_MPIO_COVERAGE_RATIO = 0.5
# 397361 filas tras agregar centro poblado -> municipio (confirmado en vivo
# 2026-10-20, de 653384 filas crudas con cantidad siempre "1").
EXPECTED_DELINCUENCIA_HURTO_MODALIDADES_MIN_COUNT = 350_000
