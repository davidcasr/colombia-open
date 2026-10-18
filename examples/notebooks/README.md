# Notebooks de ejemplo — colombia-open

Un notebook por dataset publicado, listo para abrir en Google Colab sin
instalar nada localmente. Cada notebook clona el repo, instala el extra
`pipeline` y corre el pipeline localmente para generar los datos — el
proyecto todavía no tiene un Release publicado en GitHub ni está en PyPI
(ver [Estado del proyecto](../../README.md#estado-del-proyecto)). Cuando
eso cambie, la celda de setup se reduce a `pip install colombia-open`.

| Notebook | Qué muestra | Abrir |
|---|---|---|
| [01_departamentos.ipynb](01_departamentos.ipynb) | Cargar `departamentos`, su esquema (código DIVIPOLA de 2 dígitos, nombre oficial) y búsqueda por nombre normalizado. | [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/davidcasr/colombia-open/blob/main/examples/notebooks/01_departamentos.ipynb) |
| [02_municipios.ipynb](02_municipios.ipynb) | Cargar `municipios`, filtrar por departamento, resolver nombres de ciudades (`resolve_municipios`) y el join con `departamentos` (`cross_view`). | [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/davidcasr/colombia-open/blob/main/examples/notebooks/02_municipios.ipynb) |
