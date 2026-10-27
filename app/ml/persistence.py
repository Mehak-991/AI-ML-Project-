"""Saving and loading model artifacts with joblib.

joblib uses pickle, which can execute code on load. Artifacts are therefore
only ever loaded from MODEL_DIR, by server-generated filename, after their
SHA-256 matches the hash recorded at save time. Never load user-supplied files.
"""

import hashlib
import logging
import os
import re
import uuid
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import joblib
import sklearn

from app.core.exceptions import ModelArtifactError, ModelIncompatibleError
from app.ml.training import TrainingResult
from app.utils.paths import resolve_within

logger = logging.getLogger(__name__)

ARTIFACT_FORMAT_VERSION = 1
ARTIFACT_NAME_PATTERN = re.compile(r"^[0-9a-f]{32}\.joblib$")


@dataclass(frozen=True)
class SavedArtifact:
    filename: str
    path: Path
    sha256: str
    size_bytes: int


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def save_artifact(result: TrainingResult, model_dir: Path) -> SavedArtifact:
    model_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex}.joblib"
    path = resolve_within(model_dir, filename)
    payload = {
        "format_version": ARTIFACT_FORMAT_VERSION,
        "pipeline": result.pipeline,
        "problem_type": result.problem_type,
        "algorithm": result.algorithm,
        "target_column": result.target_column,
        "feature_schema": result.feature_schema,
        "class_labels": result.class_labels,
        "metrics": result.metrics,
        "metadata": result.metadata,
    }
    temp_path = path.with_suffix(".tmp")
    joblib.dump(payload, temp_path, compress=3)
    os.replace(temp_path, path)
    return SavedArtifact(filename, path, file_sha256(path), path.stat().st_size)


def delete_artifact(model_dir: Path, filename: str) -> None:
    try:
        resolve_within(model_dir, filename).unlink(missing_ok=True)
    except (OSError, ValueError):
        logger.warning("Could not delete artifact %s", filename, exc_info=True)


def load_artifact(model_dir: Path, filename: str, expected_sha256: str) -> dict[str, Any]:
    if not ARTIFACT_NAME_PATTERN.match(filename):
        raise ModelArtifactError("Invalid artifact reference.")
    try:
        path = resolve_within(model_dir, filename)
    except ValueError:
        raise ModelArtifactError("Invalid artifact reference.") from None
    if not path.is_file():
        raise ModelArtifactError("The model artifact file is missing.")
    if file_sha256(path) != expected_sha256:
        raise ModelArtifactError("The model artifact failed its integrity check.")
    return _load_verified(str(path), expected_sha256)


def check_sklearn_compatibility(trained_with: str | None, policy: str = "strict") -> None:
    """Refuse (strict) or warn about artifacts saved with a different sklearn major.minor.

    Pickled estimators are only guaranteed to load in the exact version that wrote them;
    patch releases are normally safe, minor/major releases often are not.
    """
    if not trained_with or trained_with == sklearn.__version__:
        return
    same_minor = trained_with.split(".")[:2] == sklearn.__version__.split(".")[:2]
    if same_minor:
        return
    if policy == "strict":
        raise ModelIncompatibleError(
            f"This model was trained with scikit-learn {trained_with}; the server runs "
            f"{sklearn.__version__}. Retrain the model (or set MODEL_COMPATIBILITY_CHECK=warn).",
            details={"trained_with": trained_with, "running": sklearn.__version__},
        )
    logger.warning(
        "Model trained with scikit-learn %s, running %s", trained_with, sklearn.__version__
    )


@lru_cache(maxsize=8)
def _load_verified(path: str, sha256: str) -> dict[str, Any]:
    """Cached by (path, hash): a changed file has a new hash and is reloaded."""
    try:
        payload = joblib.load(path)
    except Exception as exc:  # unpickling can fail with almost any exception type
        # (KeyError on bad opcodes, AttributeError/ImportError on renamed classes, ...).
        logger.error("Could not unpickle model artifact: %s", type(exc).__name__)
        raise ModelIncompatibleError(
            "The stored model could not be loaded by this server version. Retrain it."
        ) from exc
    if not isinstance(payload, dict) or payload.get("format_version") != ARTIFACT_FORMAT_VERSION:
        raise ModelIncompatibleError(
            "Unsupported model artifact format version. Retrain the model.",
            details={"supported_format_version": ARTIFACT_FORMAT_VERSION},
        )
    return payload


def clear_artifact_cache() -> None:
    _load_verified.cache_clear()
