"""Feature selection, type coercion, the preprocessing transformer, and data splitting.

The same `coerce_features` runs at training and prediction time so the fitted
pipeline always sees identically typed input.
"""

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from app.ml.profiling import infer_column_kind

FeatureKind = Literal["numeric", "categorical"]
MISSING_CATEGORY = "__missing__"
MAX_ONE_HOT_CATEGORIES = 50


@dataclass(frozen=True)
class FeatureSpec:
    name: str
    kind: FeatureKind

    def to_dict(self) -> dict[str, str]:
        return {"name": self.name, "kind": self.kind}


@dataclass(frozen=True)
class DroppedColumn:
    column: str
    reason: str


def select_features(
    df: pd.DataFrame,
    target_column: str,
    *,
    include: list[str] | None = None,
    exclude: list[str] | None = None,
) -> tuple[list[FeatureSpec], list[DroppedColumn]]:
    """Choose usable feature columns and say why any others were left out."""
    candidates = include if include is not None else [c for c in df.columns if c != target_column]
    unknown = [c for c in candidates if c not in df.columns]
    if unknown:
        raise ValueError(f"Unknown feature columns: {', '.join(unknown)}")
    excluded = set(exclude or [])

    features: list[FeatureSpec] = []
    dropped: list[DroppedColumn] = []
    for column in candidates:
        series = df[column]
        kind = infer_column_kind(series)
        if column == target_column:
            dropped.append(DroppedColumn(column, "is_target"))
        elif column in excluded:
            dropped.append(DroppedColumn(column, "excluded"))
        elif series.isna().all():
            dropped.append(DroppedColumn(column, "all_missing"))
        elif series.nunique(dropna=True) <= 1:
            dropped.append(DroppedColumn(column, "constant"))
        elif kind in ("datetime", "text"):
            dropped.append(DroppedColumn(column, f"unsupported_{kind}"))
        elif kind == "numeric":
            features.append(FeatureSpec(column, "numeric"))
        else:
            features.append(FeatureSpec(column, "categorical"))
    return features, dropped


def coerce_features(df: pd.DataFrame, features: list[FeatureSpec]) -> pd.DataFrame:
    """Return only the feature columns, numeric as float and categorical as str (NaN kept)."""
    out = pd.DataFrame(index=df.index)
    for spec in features:
        series = df[spec.name]
        if spec.kind == "numeric":
            out[spec.name] = pd.to_numeric(series, errors="coerce").astype(float)
        else:
            # np.nan (not None/pd.NA) is the marker SimpleImputer recognises in object columns.
            out[spec.name] = series.map(lambda v: np.nan if pd.isna(v) else str(v)).astype(object)
    return out


def build_preprocessor(features: list[FeatureSpec]) -> ColumnTransformer:
    numeric = [f.name for f in features if f.kind == "numeric"]
    categorical = [f.name for f in features if f.kind == "categorical"]
    transformers = []
    if numeric:
        transformers.append(
            (
                "numeric",
                Pipeline(
                    [("impute", SimpleImputer(strategy="median")), ("scale", StandardScaler())]
                ),
                numeric,
            )
        )
    if categorical:
        transformers.append(
            (
                "categorical",
                Pipeline(
                    [
                        (
                            "impute",
                            SimpleImputer(
                                strategy="constant",
                                fill_value=MISSING_CATEGORY,
                                missing_values=np.nan,
                            ),
                        ),
                        (
                            "encode",
                            OneHotEncoder(
                                handle_unknown="infrequent_if_exist",
                                max_categories=MAX_ONE_HOT_CATEGORIES,
                                sparse_output=False,
                            ),
                        ),
                    ]
                ),
                categorical,
            )
        )
    if not transformers:
        raise ValueError("At least one feature column is required.")
    return ColumnTransformer(transformers, remainder="drop", verbose_feature_names_out=False)


def drop_duplicate_rows(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    deduplicated = df.drop_duplicates(keep="first")
    return deduplicated, len(df) - len(deduplicated)


@dataclass
class DataSplits:
    X_train: pd.DataFrame
    X_val: pd.DataFrame
    X_test: pd.DataFrame
    y_train: pd.Series
    y_val: pd.Series
    y_test: pd.Series
    stratified: bool

    def sizes(self) -> dict[str, int]:
        return {"train": len(self.X_train), "validation": len(self.X_val), "test": len(self.X_test)}


def split_dataset(
    X: pd.DataFrame,
    y: pd.Series,
    *,
    test_size: float = 0.2,
    validation_size: float = 0.2,
    random_state: int = 42,
    stratify: bool = False,
) -> DataSplits:
    """Split into train/validation/test. Sizes are fractions of the full dataset.

    Stratification is attempted for classification and silently skipped if a
    class is too rare to appear in every split (reported via `stratified`).
    """
    if not 0 < test_size < 1 or not 0 <= validation_size < 1 or test_size + validation_size >= 1:
        raise ValueError("test_size and validation_size must be in (0, 1) and sum to less than 1.")

    def _split(features, target, size):
        if stratify:
            try:
                return (
                    *train_test_split(
                        features, target, test_size=size, random_state=random_state, stratify=target
                    ),
                    True,
                )
            except ValueError:
                pass
        return (
            *train_test_split(features, target, test_size=size, random_state=random_state),
            False,
        )

    X_rest, X_test, y_rest, y_test, strat_test = _split(X, y, test_size)
    if validation_size:
        relative = validation_size / (1 - test_size)
        X_train, X_val, y_train, y_val, strat_val = _split(X_rest, y_rest, relative)
    else:
        X_train, y_train = X_rest, y_rest
        X_val, y_val = X_rest.iloc[0:0], y_rest.iloc[0:0]
        strat_val = strat_test
    return DataSplits(X_train, X_val, X_test, y_train, y_val, y_test, strat_test and strat_val)
