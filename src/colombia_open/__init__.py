"""colombia-open: datasets públicos de Colombia, curados y listos para usar.

from colombia_open import ColombiaOpen
hub = ColombiaOpen()
df = hub.load_polars("municipios")
"""

from .core import ColombiaOpen as ColombiaOpen
from .datasets import Dataset as Dataset
from .exceptions import ColombiaOpenCacheError as ColombiaOpenCacheError
from .exceptions import ColombiaOpenDataError as ColombiaOpenDataError
from .exceptions import ColombiaOpenDatasetError as ColombiaOpenDatasetError
from .exceptions import ColombiaOpenError as ColombiaOpenError
from .exceptions import ColombiaOpenOutputError as ColombiaOpenOutputError

__version__ = "0.1.0"

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
