"""Command line interface: download -> process -> report."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from . import analysis, filters, io, plots

SHORT_NAME = "GEDI02_A"  # GEDI L2A Elevation and Height Metrics


def _granule_size_mb(granule) -> float:
    """Granule size in MB. earthaccess exposes ``size`` as a property; older or
    newer versions may expose a method, so handle both."""
    s = granule.size
    s = s() if callable(s) else s
    try:
        return float(s)
    except (TypeError, ValueError):
        return 0.0


def cmd_download(a: argparse.Namespace) -> None:
    import earthaccess  # imported lazily; needs a free NASA Earthdata login

    earthaccess.login(strategy="environment" if a.env_login else "interactive")
    west, south, east, north = a.bbox
    results = earthaccess.search_data(
        short_name=SHORT_NAME,
        bounding_box=(west, south, east, north),
        temporal=(a.start, a.end),
    )
    print(f"Found {len(results)} granules for the bounding box and dates.")
    if a.max_granules:
        results = results[: a.max_granules]
    if not results:
        return
    size_mb = sum(_granule_size_mb(r) for r in results)
    print(f"Downloading {len(results)} granules (about {size_mb:,.0f} MB) to {a.out}")
    Path(a.out).mkdir(parents=True, exist_ok=True)
    earthaccess.download(results, a.out)


def cmd_process(a: argparse.Namespace) -> None:
    df = io.read_directory(a.raw)
    west, south, east, north = a.bbox if a.bbox else (-180, -90, 180, 90)
    df = df[df["lon"].between(west, east) & df["lat"].between(south, north)]
    df = filters.add_time_columns(df)
    df, report = filters.apply_quality(df, min_sensitivity=a.min_sensitivity)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(a.out, index=False, compression="gzip")
    print(json.dumps(report, indent=2))
    print(f"Wrote {len(df):,} filtered shots to {a.out}")


def cmd_report(a: argparse.Namespace) -> None:
    df = pd.read_csv(a.shots)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    grid = analysis.grid_stats(df, a.resolution, a.min_shots)
    yearly = analysis.yearly_summary(df)
    prof = analysis.mean_profile(df)
    grid.to_csv(out / "grid_stats.csv", index=False)
    yearly.to_csv(out / "yearly_summary.csv", index=False)
    prof.to_csv(out / "mean_profile_by_year.csv")

    plots.plot_height_map(grid, out / "height_map.png", "Median canopy height (RH98)")
    plots.plot_yearly(yearly, out / "height_by_year.png")
    plots.plot_profiles(prof, out / "mean_profiles.png")

    summary = {
        "n_shots": int(len(df)),
        "years": sorted(int(y) for y in df["year"].unique()),
        "grid_resolution_deg": a.resolution,
        "n_grid_cells": int(len(grid)),
    }
    years = summary["years"]
    if len(years) >= 2:
        mid = len(years) // 2
        early, late = tuple(years[:mid]), tuple(years[mid:])
        if a.early:
            early = tuple(a.early)
        if a.late:
            late = tuple(a.late)
        cm = analysis.change_map(df, early, late, a.resolution, a.min_shots)
        cm.to_csv(out / "change_map.csv", index=False)
        if len(cm):
            fmt = lambda ys: ", ".join(str(y) for y in ys)  # noqa: E731
            plots.plot_change(cm, out / "change_map.png",
                              f"Change in median RH98: {fmt(late)} vs {fmt(early)}")
        summary["change"] = {"early_years": list(early), "late_years": list(late),
                             **analysis.summarize_change(cm)}
    (out / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="gedi-forest", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("download", help="Download GEDI L2A granules from NASA Earthdata")
    d.add_argument("--bbox", type=float, nargs=4, required=True,
                   metavar=("WEST", "SOUTH", "EAST", "NORTH"))
    d.add_argument("--start", default="2019-04-18")
    d.add_argument("--end", default="2023-03-01")
    d.add_argument("--max-granules", type=int, default=0, help="0 = all found")
    d.add_argument("--out", default="data/raw")
    d.add_argument("--env-login", action="store_true",
                   help="Use EARTHDATA_USERNAME / EARTHDATA_PASSWORD from the environment")
    d.set_defaults(func=cmd_download)

    q = sub.add_parser("process", help="Read granules, filter shots, write a table")
    q.add_argument("--raw", default="data/raw")
    q.add_argument("--bbox", type=float, nargs=4,
                   metavar=("WEST", "SOUTH", "EAST", "NORTH"))
    q.add_argument("--min-sensitivity", type=float, default=0.95)
    q.add_argument("--out", default="data/processed/shots.csv.gz")
    q.set_defaults(func=cmd_process)

    r = sub.add_parser("report", help="Grid, summarise and plot")
    r.add_argument("--shots", default="data/processed/shots.csv.gz")
    r.add_argument("--out", default="results")
    r.add_argument("--resolution", type=float, default=0.01)
    r.add_argument("--min-shots", type=int, default=5)
    r.add_argument("--early", type=int, nargs="+")
    r.add_argument("--late", type=int, nargs="+")
    r.set_defaults(func=cmd_report)
    return p


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
