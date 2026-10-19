"""colombia-open: datasets públicos de Colombia, curados y listos para usar.

from colombia_open import ColombiaOpen
hub = ColombiaOpen()
df = hub.load_polars("municipios")
"""

from importlib.metadata import PackageNotFoundError, version

from .core import ColombiaOpen as ColombiaOpen
from .datasets import Dataset as Dataset
from .exceptions import ColombiaOpenCacheError as ColombiaOpenCacheError
from .exceptions import ColombiaOpenDataError as ColombiaOpenDataError
from .exceptions import ColombiaOpenDatasetError as ColombiaOpenDatasetError
from .exceptions import ColombiaOpenError as ColombiaOpenError
from .exceptions import ColombiaOpenOutputError as ColombiaOpenOutputError

# Leída de la metadata instalada, no hardcodeada: pyproject.toml es la única
# fuente de verdad de la versión (estuvo fija en "0.1.0" hasta 0.3.0).
try:
    __version__ = version("colombia-open")
except PackageNotFoundError:  # corriendo desde el árbol sin instalar
    __version__ = "0.0.0+unknown"

__all__ = [
    "ColombiaOpen",
    "ColombiaOpenCacheError",
    "ColombiaOpenDataError",
    "ColombiaOpenDatasetError",
    "ColombiaOpenError",
    "ColombiaOpenOutputError",
    "Dataset",
    "__version__",
]
