import pandas as pd

from app.ml.synthetic import make_classification_frame, make_regression_frame
from app.ml.visualization import generate_report_figures


def test_synthetic_data_is_reproducible() -> None:
    pd.testing.assert_frame_equal(
        make_classification_frame(seed=1), make_classification_frame(seed=1)
    )
    assert not make_classification_frame(seed=1).equals(make_classification_frame(seed=2))


def test_synthetic_data_shape_and_noise() -> None:
    df = make_regression_frame(n_rows=100, n_duplicates=4)
    assert len(df) == 104
    assert df.duplicated().sum() >= 4
    assert df["num_a"].isna().any() and df["cat_b"].isna().any()
    assert df["value"].notna().all()


def test_report_figures_are_written(tmp_path) -> None:
    paths = generate_report_figures(make_classification_frame(60), tmp_path / "figs")
    assert {p.name for p in paths} == {
        "missing_values.png",
        "numeric_distributions.png",
        "correlation.png",
    }
    for path in paths:
        assert path.read_bytes().startswith(b"\x89PNG")


def test_report_figures_skip_inapplicable_plots(tmp_path) -> None:
    paths = generate_report_figures(pd.DataFrame({"c": ["a", "b"]}), tmp_path)
    assert [p.name for p in paths] == ["missing_values.png"]
