"""Small, seeded synthetic datasets for demos and tests.

Columns are deliberately generic (num_*, cat_*) — this is not real business
data. A few missing values and exact duplicate rows are injected so cleaning
and validation code paths are exercised.
"""

import numpy as np
import pandas as pd


def _base_features(rng: np.random.Generator, n_rows: int) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "num_a": rng.normal(50, 10, n_rows).round(2),
            "num_b": rng.uniform(0, 1, n_rows).round(4),
            "num_c": rng.integers(0, 20, n_rows),
            "cat_a": rng.choice(["red", "green", "blue"], n_rows),
            "cat_b": rng.choice(["small", "medium", "large"], n_rows, p=[0.5, 0.3, 0.2]),
        }
    )


def _inject_noise(df: pd.DataFrame, rng: np.random.Generator, n_duplicates: int) -> pd.DataFrame:
    df = df.copy()
    for column in ("num_a", "cat_b"):
        idx = rng.choice(len(df), size=max(1, len(df) // 50), replace=False)
        df.loc[idx, column] = np.nan
    if n_duplicates:
        df = pd.concat([df, df.iloc[:n_duplicates]], ignore_index=True)
    return df


def make_classification_frame(
    n_rows: int = 300, seed: int = 42, n_duplicates: int = 5
) -> pd.DataFrame:
    """Binary target `label` ("yes"/"no") that depends on num_a, num_b and cat_a."""
    rng = np.random.default_rng(seed)
    df = _base_features(rng, n_rows)
    score = (
        0.08 * (df["num_a"] - 50)
        + 3 * (df["num_b"] - 0.5)
        + df["cat_a"].map({"red": 1.0, "green": 0.0, "blue": -1.0})
        + rng.normal(0, 0.5, n_rows)
    )
    df["label"] = np.where(score > 0, "yes", "no")
    return _inject_noise(df, rng, n_duplicates)


def make_regression_frame(n_rows: int = 300, seed: int = 42, n_duplicates: int = 5) -> pd.DataFrame:
    """Continuous target `value` that depends linearly on features plus noise."""
    rng = np.random.default_rng(seed)
    df = _base_features(rng, n_rows)
    df["value"] = (
        2.0 * df["num_a"]
        + 30 * df["num_b"]
        - 1.5 * df["num_c"]
        + df["cat_b"].map({"small": 0.0, "medium": 10.0, "large": 25.0})
        + rng.normal(0, 5, n_rows)
    ).round(3)
    return _inject_noise(df, rng, n_duplicates)
