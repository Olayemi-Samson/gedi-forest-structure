"""Figures for the GEDI forest structure report (matplotlib, headless)."""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402


def _save(fig, path: Path) -> Path:
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def plot_height_map(grid: pd.DataFrame, path: Path, title: str) -> Path:
    fig, ax = plt.subplots(figsize=(7, 6))
    sc = ax.scatter(grid["lon"], grid["lat"], c=grid["median"], s=14,
                    marker="s", cmap="YlGn", vmin=0, vmax=40)
    fig.colorbar(sc, ax=ax, label="Median RH98 (m)")
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.set_title(title)
    ax.set_aspect("equal")
    return _save(fig, path)


def plot_yearly(summary: pd.DataFrame, path: Path) -> Path:
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.fill_between(summary["year"], summary["p10"], summary["p90"], alpha=0.25,
                    label="10th-90th percentile")
    ax.plot(summary["year"], summary["median"], marker="o", label="Median RH98")
    for _, r in summary.iterrows():
        ax.annotate(f"n={int(r['n']):,}", (r["year"], r["median"]),
                    textcoords="offset points", xytext=(0, 8), ha="center", fontsize=7)
    ax.set_xlabel("Year")
    ax.set_ylabel("RH98 (m)")
    ax.set_xticks(list(summary["year"]))
    ax.legend()
    ax.set_title("Canopy height by year (shot counts annotated)")
    return _save(fig, path)


def plot_profiles(prof: pd.DataFrame, path: Path) -> Path:
    fig, ax = plt.subplots(figsize=(5, 6))
    for year, row in prof.iterrows():
        ax.plot(row.values, row.index, marker=".", label=str(year))
    ax.set_xlabel("Mean height above ground (m)")
    ax.set_ylabel("Waveform energy percentile (RH)")
    ax.set_title("Mean relative-height profile")
    ax.legend(title="Year")
    return _save(fig, path)


def plot_change(cm: pd.DataFrame, path: Path, title: str) -> Path:
    fig, ax = plt.subplots(figsize=(7, 6))
    lim = max(5.0, float(cm["delta_median"].abs().quantile(0.98))) if len(cm) else 5.0
    sc = ax.scatter(cm["lon"], cm["lat"], c=cm["delta_median"], s=14, marker="s",
                    cmap="RdBu", vmin=-lim, vmax=lim)
    fig.colorbar(sc, ax=ax, label="Change in median RH98 (m)")
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.set_title(title)
    ax.set_aspect("equal")
    return _save(fig, path)
