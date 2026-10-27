"""Use cases for uploading, validating and summarizing datasets."""

import logging
import tempfile
import uuid
from pathlib import Path
from typing import Any, BinaryIO

import pandas as pd
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import DataValidationError, InvalidFileError, NotFoundError
from app.database.models import Dataset
from app.ml.ingestion import read_tabular_file
from app.ml.profiling import column_schema, summarize_dataframe
from app.ml.validation import ValidationReport, validate_dataframe
from app.repositories.datasets import DatasetRepository
from app.services.storage import StoredFile, delete_stored_file, store_upload
from app.utils.paths import resolve_within

logger = logging.getLogger(__name__)


def _read(settings: Settings, path: Path, file_format: str) -> pd.DataFrame:
    return read_tabular_file(
        path,
        file_format,
        max_rows=settings.MAX_DATASET_ROWS,
        max_columns=settings.MAX_DATASET_COLUMNS,
    )


def validate_upload(
    settings: Settings, source: BinaryIO, filename: str | None, target_column: str | None
) -> tuple[StoredFile, ValidationReport, dict[str, Any]]:
    """Validate and summarize an upload without persisting anything."""
    with tempfile.TemporaryDirectory(prefix="aiproject-validate-") as tmp:
        stored = store_upload(source, filename, Path(tmp), max_bytes=settings.max_upload_bytes)
        frame = _read(settings, stored.path, stored.file_format)
    report = validate_dataframe(frame, target_column=target_column)
    return stored, report, summarize_dataframe(frame)


def create_dataset(
    session: Session,
    settings: Settings,
    source: BinaryIO,
    filename: str | None,
    name: str | None = None,
) -> tuple[Dataset, ValidationReport]:
    """Store an upload, reject structurally invalid data, and record it in the DB."""
    stored = store_upload(source, filename, settings.UPLOAD_DIR, max_bytes=settings.max_upload_bytes)
    try:
        frame = _read(settings, stored.path, stored.file_format)
        report = validate_dataframe(frame)
        if not report.is_valid:
            raise DataValidationError(
                "The dataset failed validation.", details=report.to_dict()["errors"]
            )
        dataset = Dataset(
            name=(name or Path(stored.original_filename).stem)[:255],
            original_filename=stored.original_filename,
            stored_filename=stored.stored_filename,
            file_format=stored.file_format,
            size_bytes=stored.size_bytes,
            sha256=stored.sha256,
            n_rows=len(frame),
            n_columns=frame.shape[1],
            columns=column_schema(frame),
        )
        DatasetRepository(session).add(dataset)
        session.commit()
    except BaseException:
        session.rollback()
        delete_stored_file(settings.UPLOAD_DIR, stored.stored_filename)
        raise
    logger.info("Stored dataset %s (%d rows)", dataset.id, dataset.n_rows)
    return dataset, report


def get_dataset(session: Session, dataset_id: uuid.UUID) -> Dataset:
    dataset = DatasetRepository(session).get(dataset_id)
    if dataset is None:
        raise NotFoundError(f"Dataset {dataset_id} not found.")
    return dataset


def load_dataset_frame(settings: Settings, dataset: Dataset) -> pd.DataFrame:
    try:
        path = resolve_within(settings.UPLOAD_DIR, dataset.stored_filename)
    except ValueError:
        raise InvalidFileError("The dataset's stored file reference is invalid.") from None
    if not path.is_file():
        raise NotFoundError("The dataset's file is missing from storage.")
    return _read(settings, path, dataset.file_format)


def summarize_dataset(
    settings: Settings, dataset: Dataset, target_column: str | None = None
) -> tuple[ValidationReport, dict[str, Any]]:
    frame = load_dataset_frame(settings, dataset)
    return validate_dataframe(frame, target_column=target_column), summarize_dataframe(frame)
