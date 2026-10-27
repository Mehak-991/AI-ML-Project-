import io
import zipfile

import pandas as pd
import pytest

from app.core.exceptions import (
    DataValidationError,
    FileTooLargeError,
    InvalidFileError,
    UnsupportedFileTypeError,
)
from app.ml.ingestion import detect_file_format, read_tabular_file
from app.services.storage import store_upload
from app.utils.paths import resolve_within, sanitize_display_filename
from tests.helpers import to_csv_bytes, to_xlsx_bytes, write_bytes

LIMITS = {"max_rows": 1000, "max_columns": 50}


# --- ingestion ---------------------------------------------------------------------


def test_reads_csv(tmp_path, classification_df) -> None:
    path = write_bytes(tmp_path / "d.csv", to_csv_bytes(classification_df))
    frame = read_tabular_file(path, "csv", **LIMITS)
    assert frame.shape == classification_df.shape
    assert list(frame.columns) == list(classification_df.columns)


def test_reads_csv_with_utf8_bom(tmp_path) -> None:
    path = write_bytes(tmp_path / "d.csv", "\ufeffa,b\n1,x\n".encode())
    assert list(read_tabular_file(path, "csv", **LIMITS).columns) == ["a", "b"]


def test_reads_xlsx(tmp_path, classification_df) -> None:
    path = write_bytes(tmp_path / "d.xlsx", to_xlsx_bytes(classification_df))
    frame = read_tabular_file(path, "excel", **LIMITS)
    assert frame.shape == classification_df.shape


@pytest.mark.parametrize("name", ["data.txt", "data.xls", "data.json", "noext", "data.csv.exe"])
def test_unsupported_extensions(name: str) -> None:
    with pytest.raises(UnsupportedFileTypeError):
        detect_file_format(name)


def test_extension_is_case_insensitive() -> None:
    assert detect_file_format("DATA.CSV") == "csv"
    assert detect_file_format("Book.XLSX") == "excel"


@pytest.mark.parametrize(
    ("content", "error"),
    [
        (b"", InvalidFileError),
        (b"a,b\n1,2,3,4\n5\n", InvalidFileError),  # ragged rows
        ("a,b\n\xe9,1\n".encode("latin-1"), InvalidFileError),  # not UTF-8
        (b"a,a\n1,2\n", DataValidationError),  # duplicate header
    ],
)
def test_invalid_csv(tmp_path, content: bytes, error: type[Exception]) -> None:
    path = write_bytes(tmp_path / "bad.csv", content)
    with pytest.raises(error):
        read_tabular_file(path, "csv", **LIMITS)


def test_fake_xlsx_is_rejected(tmp_path) -> None:
    path = write_bytes(tmp_path / "fake.xlsx", b"just text pretending to be a workbook")
    with pytest.raises(InvalidFileError):
        read_tabular_file(path, "excel", **LIMITS)


def test_zip_that_is_not_a_workbook_is_rejected(tmp_path) -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("hello.txt", "hi")
    path = write_bytes(tmp_path / "x.xlsx", buffer.getvalue())
    with pytest.raises(InvalidFileError, match="not a valid .xlsx"):
        read_tabular_file(path, "excel", **LIMITS)


def test_highly_compressed_xlsx_is_rejected(tmp_path) -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<x/>")
        archive.writestr("xl/bomb.xml", "0" * 5_000_000)
    path = write_bytes(tmp_path / "bomb.xlsx", buffer.getvalue())
    with pytest.raises(InvalidFileError, match="suspiciously large"):
        read_tabular_file(path, "excel", **LIMITS)


def test_row_and_column_limits(tmp_path) -> None:
    path = write_bytes(tmp_path / "d.csv", to_csv_bytes(pd.DataFrame({"a": range(20)})))
    with pytest.raises(DataValidationError, match="rows"):
        read_tabular_file(path, "csv", max_rows=10, max_columns=5)
    wide = pd.DataFrame([list(range(8))], columns=[f"c{i}" for i in range(8)])
    path = write_bytes(tmp_path / "w.csv", to_csv_bytes(wide))
    with pytest.raises(DataValidationError, match="columns"):
        read_tabular_file(path, "csv", max_rows=10, max_columns=5)


# --- storage and paths -------------------------------------------------------------


def test_store_upload_uses_generated_name(tmp_path) -> None:
    stored = store_upload(
        io.BytesIO(b"a,b\n1,2\n"), "../../etc/passwd.csv", tmp_path, max_bytes=1024
    )
    assert stored.path.parent == tmp_path.resolve()
    assert stored.original_filename == "passwd.csv"
    assert stored.stored_filename.endswith(".csv")
    assert ".." not in stored.stored_filename
    assert stored.size_bytes == 8
    assert len(stored.sha256) == 64


def test_store_upload_enforces_size_limit_and_cleans_up(tmp_path) -> None:
    with pytest.raises(FileTooLargeError):
        store_upload(io.BytesIO(b"a\n" + b"1\n" * 600), "big.csv", tmp_path, max_bytes=100)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    ("content", "filename"),
    [
        (b"", "empty.csv"),
        (b"a,b\n\x00\x01\x02", "binary.csv"),
        (b"\xff\xfe\x00a", "utf16.csv"),
        (b"a,b\n1,2", "not-really.xlsx"),
    ],
)
def test_store_upload_rejects_bad_content(tmp_path, content: bytes, filename: str) -> None:
    with pytest.raises(InvalidFileError):
        store_upload(io.BytesIO(content), filename, tmp_path, max_bytes=1024)
    assert list(tmp_path.iterdir()) == []


def test_store_upload_rejects_unsupported_type(tmp_path) -> None:
    with pytest.raises(UnsupportedFileTypeError):
        store_upload(io.BytesIO(b"MZ"), "evil.exe", tmp_path, max_bytes=1024)


@pytest.mark.parametrize(
    "name",
    ["../secret.csv", "..\\secret.csv", "/etc/passwd", "C:\\Windows\\x.csv", "a/b.csv", "..", ""],
)
def test_resolve_within_rejects_traversal(tmp_path, name: str) -> None:
    with pytest.raises(ValueError):
        resolve_within(tmp_path, name)


def test_resolve_within_accepts_generated_names(tmp_path) -> None:
    assert resolve_within(tmp_path, "abc123.csv") == (tmp_path / "abc123.csv").resolve()


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("report.csv", "report.csv"),
        ("../../x.csv", "x.csv"),
        ("C:\\Users\\me\\data.xlsx", "data.xlsx"),
        ("bad<>name|.csv", "badname.csv"),
        (None, "upload"),
        ("...", "upload"),
    ],
)
def test_sanitize_display_filename(raw, expected: str) -> None:
    assert sanitize_display_filename(raw) == expected
