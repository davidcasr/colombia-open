"""Excepciones públicas de colombia-open."""

from __future__ import annotations


class ColombiaOpenError(Exception):
    """Base para todos los errores de la librería."""


class ColombiaOpenDatasetError(ColombiaOpenError):
    """Dataset no existe o nombre inválido."""


class ColombiaOpenOutputError(ColombiaOpenError):
    """El dataset existe pero no tiene el output solicitado."""


class ColombiaOpenDataError(ColombiaOpenError):
    """Los datos existen pero no pasan validación."""


class ColombiaOpenCacheError(ColombiaOpenError):
    """Falló la descarga/verificación del bundle de datos."""
