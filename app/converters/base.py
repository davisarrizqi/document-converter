"""Converter contract and lookup."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class ConversionFailed(Exception):
    """The converter could not produce a usable file. The message is for logs."""


class DocumentConverter(ABC):
    source_format: str
    target_format: str

    @abstractmethod
    def convert(self, source: Path, target: Path) -> None:
        """Write the converted document to ``target``. Raise ConversionFailed on failure."""


class ConverterRegistry:
    def __init__(self, converters: list[DocumentConverter]) -> None:
        self._converters = {
            (converter.source_format, converter.target_format): converter for converter in converters
        }

    def get(self, source_format: str, target_format: str) -> DocumentConverter | None:
        return self._converters.get((source_format, target_format))
