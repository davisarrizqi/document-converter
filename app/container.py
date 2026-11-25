"""Wires settings, storage, repositories, and services together."""

from __future__ import annotations

from dataclasses import dataclass

from app.config import Settings
from app.converters.base import ConverterRegistry
from app.database import Database
from app.services.conversions import ConversionService
from app.services.documents import DocumentService
from app.storage import StoredFiles


@dataclass
class Container:
    settings: Settings
    database: Database
    files: StoredFiles
    documents: DocumentService
    conversions: ConversionService

    def __init__(
        self,
        *,
        settings: Settings,
        database: Database,
        files: StoredFiles,
        converters: ConverterRegistry,
    ) -> None:
        self.settings = settings
        self.database = database
        self.files = files
        self.documents = DocumentService(database, files)
        self.conversions = ConversionService(database, files, converters, settings)
