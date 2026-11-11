"""Shared input validation for text-in AI services (independent of the HTTP layer)."""

from app.core.exceptions import DataValidationError


def validate_texts(texts: list[str], *, max_texts: int, max_chars: int) -> list[str]:
    """Reject empty batches, oversized batches, blank texts and overly long texts."""
    if not isinstance(texts, list) or not texts:
        raise DataValidationError("At least one text is required.")
    if len(texts) > max_texts:
        raise DataValidationError(f"At most {max_texts} texts per request.")
    errors = []
    for index, text in enumerate(texts):
        if not isinstance(text, str) or not text.strip():
            errors.append({"index": index, "message": "Text must be a non-empty string."})
        elif len(text) > max_chars:
            errors.append({"index": index, "message": f"Text exceeds {max_chars} characters."})
    if errors:
        raise DataValidationError("Invalid input texts.", details=errors[:50])
    return texts
