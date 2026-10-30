"""Unit tests for Phase 11 statistical drift detection algorithms and data quality metrics."""

import math
import numpy as np
import pandas as pd
from scipy import stats

from app.services.drift_service import (
    _drift_status_from_ks,
    _drift_status_from_psi,
    _psi_categorical,
    _psi_numeric,
)


def test_psi_identical_numeric_distributions():
    np.random.seed(42)
    reference = np.random.normal(0, 1, 1000)
    production = np.random.normal(0, 1, 1000)
    psi = _psi_numeric(reference, production)
    assert not math.isnan(psi)
    assert psi < 0.1
    status = _drift_status_from_psi(psi)
    assert status == "normal"


def test_psi_mild_drift():
    np.random.seed(42)
    reference = np.random.normal(0, 1, 2000)
    production = np.random.normal(0.3, 1.1, 2000)
    psi = _psi_numeric(reference, production)
    assert not math.isnan(psi)
    assert 0.05 <= psi < 0.35


def test_psi_significant_drift():
    np.random.seed(42)
    reference = np.random.normal(0, 1, 1000)
    production = np.random.normal(2.5, 1.5, 1000)
    psi = _psi_numeric(reference, production)
    assert not math.isnan(psi)
    assert psi >= 0.2
    status = _drift_status_from_psi(psi)
    assert status == "critical"


def test_psi_categorical_distributions():
    ref_series = pd.Series(["A"] * 500 + ["B"] * 300 + ["C"] * 200)
    prod_same = pd.Series(["A"] * 250 + ["B"] * 150 + ["C"] * 100)
    prod_drift = pd.Series(["A"] * 50 + ["B"] * 100 + ["C"] * 400)

    psi_same = _psi_categorical(ref_series, prod_same)
    assert psi_same < 0.05
    assert _drift_status_from_psi(psi_same) == "normal"

    psi_drift = _psi_categorical(ref_series, prod_drift)
    assert psi_drift >= 0.2
    assert _drift_status_from_psi(psi_drift) == "critical"


def test_ks_test_and_status():
    np.random.seed(42)
    ref = np.random.normal(10, 2, 800)
    prod_same = np.random.normal(10, 2, 800)
    prod_diff = np.random.exponential(5, 800)

    _, ks_p_same = stats.ks_2samp(ref, prod_same)
    assert ks_p_same > 0.05
    assert _drift_status_from_ks(ks_p_same) == "normal"

    _, ks_p_diff = stats.ks_2samp(ref, prod_diff)
    assert ks_p_diff < 0.001
    assert _drift_status_from_ks(ks_p_diff) == "critical"


def test_psi_edge_cases():
    # Empty or insufficient samples
    empty_arr = np.array([])
    small_arr = np.array([1.0, 2.0])
    psi_small = _psi_numeric(empty_arr, small_arr)
    assert math.isnan(psi_small)
    assert _drift_status_from_psi(psi_small) == "insufficient_data"
