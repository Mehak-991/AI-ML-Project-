"""Static report figures (PNG) for exploratory data summaries.

Uses the non-interactive Agg backend so it works on servers without a display.
"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

MAX_DISTRIBUTION_PLOTS = 12


def plot_missing_values(df: pd.DataFrame, path: Path) -> Path:
    ratios = df.isna().mean().sort_values(ascending=False)
    fig, ax = plt.subplots(figsize=(8, max(3, 0.3 * len(ratios))))
    sns.barplot(x=ratios.values, y=ratios.index.astype(str), ax=ax, color="#4C72B0")
    ax.set_xlim(0, 1)
    ax.set_xlabel("Missing ratio")
    ax.set_title("Missing values by column")
    fig.tight_layout()
    fig.savefig(path, dpi=100)
    plt.close(fig)
    return path


def plot_numeric_distributions(df: pd.DataFrame, path: Path) -> Path | None:
    numeric = df.select_dtypes("number").columns[:MAX_DISTRIBUTION_PLOTS]
    if len(numeric) == 0:
        return None
    cols = min(3, len(numeric))
    rows = -(-len(numeric) // cols)
    fig, axes = plt.subplots(rows, cols, figsize=(4 * cols, 3 * rows), squeeze=False)
    for ax, column in zip(axes.flat, numeric, strict=False):
        sns.histplot(df[column].dropna(), ax=ax, bins=30)
        ax.set_title(str(column))
    for ax in list(axes.flat)[len(numeric) :]:
        ax.set_visible(False)
    fig.tight_layout()
    fig.savefig(path, dpi=100)
    plt.close(fig)
    return path


def plot_correlation_heatmap(df: pd.DataFrame, path: Path) -> Path | None:
    numeric = df.select_dtypes("number")
    if numeric.shape[1] < 2:
        return None
    fig, ax = plt.subplots(figsize=(1 + 0.6 * numeric.shape[1], 0.6 * numeric.shape[1] + 1))
    sns.heatmap(numeric.corr(), annot=True, fmt=".2f", cmap="vlag", vmin=-1, vmax=1, ax=ax)
    ax.set_title("Correlation (numeric columns)")
    fig.tight_layout()
    fig.savefig(path, dpi=100)
    plt.close(fig)
    return path


def generate_report_figures(df: pd.DataFrame, output_dir: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    figures = [
        plot_missing_values(df, output_dir / "missing_values.png"),
        plot_numeric_distributions(df, output_dir / "numeric_distributions.png"),
        plot_correlation_heatmap(df, output_dir / "correlation.png"),
    ]
    return [path for path in figures if path is not None]
