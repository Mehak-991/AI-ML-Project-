import numpy as np
import pandas as pd
import pytest

from app.ml.preprocessing import (
    MISSING_CATEGORY,
    FeatureSpec,
    build_preprocessor,
    coerce_features,
    drop_duplicate_rows,
    select_features,
    split_dataset,
)


def test_select_features_reports_dropped_columns() -> None:
    df = pd.DataFrame(
        {
            "num": [1.0, 2.0, 3.0, 4.0],
            "cat": ["a", "b", "a", "b"],
            "flag": [True, False, True, True],
            "const": [1, 1, 1, 1],
            "empty": [None] * 4,
            "when": pd.to_datetime(["2024-01-01"] * 2 + ["2024-02-01"] * 2),
            "secret_id": [10, 11, 12, 13],
            "target": [0, 1, 0, 1],
        }
    )
    features, dropped = select_features(df, "target", exclude=["secret_id"])
    assert features == [
        FeatureSpec("num", "numeric"),
        FeatureSpec("cat", "categorical"),
        FeatureSpec("flag", "categorical"),
    ]
    reasons = {d.column: d.reason for d in dropped}
    assert reasons == {
        "const": "constant",
        "empty": "all_missing",
        "when": "unsupported_datetime",
        "secret_id": "excluded",
    }


def test_select_features_never_includes_target() -> None:
    df = pd.DataFrame({"a": [1, 2, 3], "t": [0, 1, 0]})
    features, dropped = select_features(df, "t", include=["a", "t"])
    assert [f.name for f in features] == ["a"]
    assert dropped[0].reason == "is_target"


def test_select_features_unknown_column() -> None:
    with pytest.raises(ValueError, match="Unknown feature"):
        select_features(pd.DataFrame({"a": [1]}), "a", include=["nope"])


def test_coerce_features_types() -> None:
    df = pd.DataFrame({"n": ["1", "2.5", None], "c": [1, None, True], "extra": [1, 2, 3]})
    out = coerce_features(df, [FeatureSpec("n", "numeric"), FeatureSpec("c", "categorical")])
    assert list(out.columns) == ["n", "c"]
    assert out["n"].dtype == float
    assert np.isnan(out["n"].iloc[2])
    assert out["c"].tolist()[0] == "1"
    assert pd.isna(out["c"].iloc[1])
    assert out["c"].iloc[2] == "True"


def test_preprocessor_imputes_scales_and_encodes() -> None:
    specs = [FeatureSpec("n", "numeric"), FeatureSpec("c", "categorical")]
    train = coerce_features(
        pd.DataFrame({"n": [1.0, 2.0, None, 4.0], "c": ["a", "b", None, "a"]}), specs
    )
    pre = build_preprocessor(specs).fit(train)
    names = list(pre.get_feature_names_out())
    assert "n" in names
    assert f"c_{MISSING_CATEGORY}" in names
    transformed = pre.transform(train)
    assert not np.isnan(transformed).any()
    # Unknown categories at inference time must not raise.
    unseen = coerce_features(pd.DataFrame({"n": [3.0], "c": ["zzz"]}), specs)
    assert pre.transform(unseen).shape == (1, len(names))


def test_preprocessor_requires_features() -> None:
    with pytest.raises(ValueError):
        build_preprocessor([])


def test_drop_duplicate_rows() -> None:
    df = pd.DataFrame({"a": [1, 1, 2], "b": ["x", "x", "y"]})
    deduped, dropped = drop_duplicate_rows(df)
    assert dropped == 1
    assert len(deduped) == 2


def test_split_sizes_and_disjointness() -> None:
    X = pd.DataFrame({"a": range(100)})
    y = pd.Series([0, 1] * 50)
    splits = split_dataset(X, y, test_size=0.2, validation_size=0.2, stratify=True)
    assert splits.sizes() == {"train": 60, "validation": 20, "test": 20}
    assert splits.stratified
    indices = [set(s.index) for s in (splits.X_train, splits.X_val, splits.X_test)]
    assert not (indices[0] & indices[1]) and not (indices[0] & indices[2])
    assert not (indices[1] & indices[2])
    assert splits.y_test.mean() == pytest.approx(0.5)


def test_split_is_reproducible() -> None:
    X = pd.DataFrame({"a": range(50)})
    y = pd.Series(range(50))
    first = split_dataset(X, y, random_state=1)
    second = split_dataset(X, y, random_state=1)
    assert first.X_test.index.equals(second.X_test.index)


def test_split_falls_back_when_class_too_rare() -> None:
    X = pd.DataFrame({"a": range(30)})
    y = pd.Series([0] * 29 + [1])
    splits = split_dataset(X, y, stratify=True)
    assert splits.stratified is False


def test_split_without_validation() -> None:
    X = pd.DataFrame({"a": range(10)})
    splits = split_dataset(X, pd.Series(range(10)), test_size=0.3, validation_size=0)
    assert splits.sizes() == {"train": 7, "validation": 0, "test": 3}


@pytest.mark.parametrize(("test", "val"), [(0, 0.2), (1.0, 0), (0.5, 0.5)])
def test_split_rejects_bad_sizes(test: float, val: float) -> None:
    with pytest.raises(ValueError):
        split_dataset(
            pd.DataFrame({"a": range(10)}),
            pd.Series(range(10)),
            test_size=test,
            validation_size=val,
        )
