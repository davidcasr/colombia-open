# Notebooks de ejemplo — colombia-open

Un notebook por dataset publicado, listo para abrir en Google Colab sin
instalar nada localmente. `colombia-open` ya está publicado en
[PyPI](https://pypi.org/project/colombia-open/) — la celda de setup de
cada notebook es simplemente `pip install colombia-open`, que descarga y
cachea el bundle de datos publicado en GitHub Releases automáticamente
(ver [Estado del proyecto](../../README.md#estado-del-proyecto)).

| Notebook | Qué muestra | Abrir |
|---|---|---|
| [01_departamentos.ipynb](01_departamentos.ipynb) | Cargar `departamentos`, su esquema (código DIVIPOLA de 2 dígitos, nombre oficial) y búsqueda por nombre normalizado. | [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/davidcasr/colombia-open/blob/main/examples/notebooks/01_departamentos.ipynb) |
| [02_municipios.ipynb](02_municipios.ipynb) | Cargar `municipios`, filtrar por departamento, resolver nombres de ciudades (`resolve_municipios`) y el join con `departamentos` (`cross_view`). | [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/davidcasr/colombia-open/blob/main/examples/notebooks/02_municipios.ipynb) |
| [03_demografia.ipynb](03_demografia.ipynb) | Cargar `demografia`, serie de tiempo de población por municipio, el join con `municipios` (`cross_view`) y la validación de integridad referencial (`validate_dataset`). | [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/davidcasr/colombia-open/blob/main/examples/notebooks/03_demografia.ipynb) |
| [04_educacion_establecimientos.ipynb](04_educacion_establecimientos.ipynb) | Cargar `educacion_establecimientos` (606k filas), filtrar establecimientos oficiales por municipio/año, el join con `municipios`, y el defecto conocido de la fuente en 2023 (`validate_dataset`). | [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/davidcasr/colombia-open/blob/main/examples/notebooks/04_educacion_establecimientos.ipynb) |
| [05_delincuencia_hurto_personas.ipynb](05_delincuencia_hurto_personas.ipynb) | Cargar `delincuencia_hurto_personas` (650k filas, víctimas por municipio y día), series anual y mensual, tasa por 100 mil habitantes con el join a `demografia`, y el defecto conocido de la fuente en 2008 (warnings del catálogo). | [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/davidcasr/colombia-open/blob/main/examples/notebooks/05_delincuencia_hurto_personas.ipynb) |
| [06_delincuencia_lesiones_personales.ipynb](06_delincuencia_lesiones_personales.ipynb) | Cargar `delincuencia_lesiones_personales` (1.38M filas, víctimas por municipio, día, conducta, arma, género y edad), separar lesiones dolosas de las de tránsito (`tipo_lesion`), desagregar por arma y género, y tasa por 100 mil habitantes con el join a `demografia`. | [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/davidcasr/colombia-open/blob/main/examples/notebooks/06_delincuencia_lesiones_personales.ipynb) |
