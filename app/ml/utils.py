"""Helpers for turning NumPy/pandas values into JSON-safe Python values."""

import math
from typing import Any

import numpy as np
import pandas as pd


def to_python(value: Any) -> Any:
    """Convert NumPy scalars to Python and NaN/inf/NaT to None."""
    if value is None or value is pd.NaT:
        return None
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    return value


def round_or_none(value: Any, digits: int = 6) -> float | None:
    value = to_python(value)
    return None if value is None else round(float(value), digits)
