"""Command line interface.

Typical order: download -> process -> report | compare | disturbance -> model.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from . import analysis, compare, disturbance, filters, io, model, plots, regions

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


def spread_evenly(items: list, n: int) -> list:
    """Pick n items spread evenly across the list (results arrive in time order, so
    taking the first n would bias the sample toward the earliest dates)."""
    if n <= 0 or len(items) <= n:
        return list(items)
    if n == 1:
        return [items[len(items) // 2]]
    idx = sorted({round(i * (len(items) - 1) / (n - 1)) for i in range(n)})
    return [items[i] for i in idx]


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
        results = spread_evenly(results, a.max_granules)
    if not results:
        return
    size_mb = sum(_granule_size_mb(r) for r in results)
    if a.dry_run:
        print(f"Dry run: would download {len(results)} granules (about {size_mb:,.0f} MB) to {a.out}")
        return
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


def cmd_regions_fetch(a: argparse.Namespace) -> None:
    for iso in a.iso:
        path = regions.fetch_boundary(iso, a.level)
        print(f"Saved {path}. Check the licence in the geoBoundaries metadata before redistributing.")


def cmd_bbox(a: argparse.Namespace) -> None:
    try:
        path = regions.bundled(a.iso, a.level)
    except FileNotFoundError:
        path = regions.fetch_boundary(a.iso, a.level)
    w, s_, e, n = regions.region_bounds(path, a.region)
    print(f"{w:.4f} {s_:.4f} {e:.4f} {n:.4f}")


def _load_labelled_regions(a: argparse.Namespace):
    labelled = []
    for iso in a.iso or []:
        try:
            path = regions.bundled(iso, a.level)
        except FileNotFoundError:
            path = regions.fetch_boundary(iso, a.level)
        labelled += [(f"{iso.upper()}: {n}", g, iso.upper()) for n, g in regions.load_regions(path)]
    for gj in a.geojson or []:
        stem = Path(gj).stem
        labelled += [(f"{stem}: {n}", g, stem) for n, g in regions.load_regions(gj, a.name_field)]
    if not labelled:
        raise SystemExit("Give --iso (e.g. NGA BRA) and/or --geojson FILE")
    return labelled


def cmd_compare(a: argparse.Namespace) -> None:
    df = pd.read_csv(a.shots)
    if "state" in df.columns and not a.all_states:
        df = df[df["state"] == "intact"]
        print("Using intact-forest shots only (add --all-states to keep everything).")
    df = df[df["rh98"] >= a.min_rh98]
    labelled = _load_labelled_regions(a)
    geoms = [(n, g) for n, g, _ in labelled]
    country_of = {n: c for n, _, c in labelled}
    df = df.assign(region=regions.assign_regions(df["lon"], df["lat"], geoms))
    df["country"] = df["region"].map(country_of)

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    by_region = compare.compare_regions(df, "region", a.min_shots, a.n_boot)
    by_country = compare.compare_regions(df, "country", a.min_shots, a.n_boot)
    by_region.to_csv(out / "by_region.csv", index=False)
    by_country.to_csv(out / "by_country.csv", index=False)
    if len(by_region):
        plots.plot_regions(by_region, out / "by_region.png", "region")
    summary = {"n_shots_assigned": int(df["region"].notna().sum()),
               "n_shots_total": int(len(df)),
               "countries": by_country.to_dict(orient="records")}
    countries = list(by_country["country"]) if len(by_country) else []
    if len(countries) >= 2:
        first, second = countries[0], countries[1]
        summary["difference"] = {"a": first, "b": second, **compare.difference_in_medians(
            df[df["country"] == first], df[df["country"] == second], n_boot=a.n_boot)}
    (out / "summary.json").write_text(json.dumps(summary, indent=2, default=float))
    print(json.dumps(summary, indent=2, default=float))


def cmd_disturbance(a: argparse.Namespace) -> None:
    df = pd.read_csv(a.shots)
    ctx = disturbance.add_disturbance_context(
        df, a.lossyear, a.treecover, tc_min=a.tc_min, max_edge_m=a.max_edge_m)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    ctx.to_csv(out / "shots_with_context.csv.gz", index=False, compression="gzip")
    edge = disturbance.edge_profile(ctx, max_edge_m=a.max_edge_m, n_boot=a.n_boot)
    rec = disturbance.recovery_curve(ctx, n_boot=a.n_boot)
    edge.to_csv(out / "edge_profile.csv", index=False)
    rec.to_csv(out / "recovery_curve.csv", index=False)
    if len(edge):
        plots.plot_edge_profile(edge, out / "edge_profile.png")
    if len(rec):
        plots.plot_recovery(rec, out / "recovery_curve.png")
    counts = ctx["state"].value_counts(dropna=False).to_dict()
    summary = {"n_shots": int(len(ctx)), "state_counts": {str(k): int(v) for k, v in counts.items()}}
    (out / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


def cmd_model(a: argparse.Namespace) -> None:
    df = pd.read_csv(a.shots)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    results = {}
    for scheme in ("spatial", "random"):
        cv = model.cross_validate(df, scheme=scheme, n_splits=a.folds, block_deg=a.block_deg)
        cv.to_csv(out / f"cv_{scheme}.csv", index=False)
        results[scheme] = model.summarize(cv)
    (out / "model_summary.json").write_text(json.dumps(results, indent=2))
    print(json.dumps(results, indent=2))
    print("Compare 'spatial' and 'random': a large gap means random CV overstates skill.")


def sanity_report(df: pd.DataFrame) -> tuple[dict, list[str]]:
    """Summarise a processed shot table and flag values that look wrong for tropical forest."""
    rh = df["rh98"].dropna()
    info = {
        "shots": int(len(df)),
        "granules": int(df["granule"].nunique()) if "granule" in df else None,
        "years": sorted(int(y) for y in df["year"].dropna().unique()) if "year" in df else [],
        "lon_range": [round(float(df["lon"].min()), 3), round(float(df["lon"].max()), 3)],
        "lat_range": [round(float(df["lat"].min()), 3), round(float(df["lat"].max()), 3)],
        "rh98_percentiles_m": {str(q): round(float(rh.quantile(q / 100)), 1) for q in (5, 25, 50, 75, 95)},
    }
    warns = []
    if len(df) < 1000:
        warns.append("Fewer than 1,000 shots: too few for reliable medians. Download more granules.")
    if len(info["years"]) < 2:
        warns.append("Only one acquisition year: change analysis needs at least two.")
    if len(rh) and float(rh.max()) > 120:
        warns.append("RH98 above 120 m: units or filtering look wrong.")
    if len(rh) and float(rh.median()) < 3:
        warns.append("Median RH98 below 3 m: this area may be mostly non-forest, or the box is wrong.")
    if len(rh) and float(rh.quantile(0.95)) < 10:
        warns.append("Almost no tall canopy (95th percentile under 10 m): check the area is forested.")
    return info, warns


def cmd_check(a: argparse.Namespace) -> None:
    df = pd.read_csv(a.shots)
    info, warns = sanity_report(df)
    print(json.dumps(info, indent=2))
    if warns:
        print("\nWARNINGS:")
        for w in warns:
            print(" -", w)
    else:
        print("\nNo obvious problems. Still look at the figures before trusting any number.")


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
    d.add_argument("--dry-run", action="store_true",
                   help="Search and report how many granules and MB, without downloading")
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

    b = sub.add_parser("bbox", help="Print 'WEST SOUTH EAST NORTH' for a region from real boundaries")
    b.add_argument("--iso", required=True)
    b.add_argument("--region", help="Region name, e.g. 'Cross River'; omit for the whole country")
    b.add_argument("--level", default="ADM1")
    b.set_defaults(func=cmd_bbox)

    f = sub.add_parser("regions-fetch", help="Download geoBoundaries admin boundaries for a country")
    f.add_argument("--iso", nargs="+", required=True, help="ISO3 codes, e.g. COD IDN")
    f.add_argument("--level", default="ADM1")
    f.set_defaults(func=cmd_regions_fetch)

    c = sub.add_parser("compare", help="Compare canopy height between regions/countries")
    c.add_argument("--shots", default="data/processed/shots.csv.gz")
    c.add_argument("--iso", nargs="*", default=["NGA", "BRA"], help="Bundled/fetchable ISO3 codes")
    c.add_argument("--geojson", nargs="*", help="Extra GeoJSON files with region polygons")
    c.add_argument("--name-field", default="shapeName")
    c.add_argument("--level", default="ADM1")
    c.add_argument("--min-shots", type=int, default=100)
    c.add_argument("--min-rh98", type=float, default=0.0)
    c.add_argument("--n-boot", type=int, default=500)
    c.add_argument("--all-states", action="store_true",
                   help="Keep non-intact shots when disturbance context is present")
    c.add_argument("--out", default="results/compare")
    c.set_defaults(func=cmd_compare)

    x = sub.add_parser("disturbance", help="Regrowth age and edge distance from Hansen forest-loss tiles")
    x.add_argument("--shots", default="data/processed/shots.csv.gz")
    x.add_argument("--lossyear", nargs="+", required=True, help="Hansen lossyear GeoTIFF tile(s)")
    x.add_argument("--treecover", nargs="+", required=True, help="Hansen treecover2000 GeoTIFF tile(s)")
    x.add_argument("--tc-min", type=float, default=30.0)
    x.add_argument("--max-edge-m", type=float, default=1000.0)
    x.add_argument("--n-boot", type=int, default=300)
    x.add_argument("--out", default="results/disturbance")
    x.set_defaults(func=cmd_disturbance)

    m = sub.add_parser("model", help="Spatially cross-validated RH98 model (needs disturbance output)")
    m.add_argument("--shots", default="results/disturbance/shots_with_context.csv.gz")
    m.add_argument("--folds", type=int, default=5)
    m.add_argument("--block-deg", type=float, default=0.25)
    m.add_argument("--out", default="results/model")
    m.set_defaults(func=cmd_model)
    k = sub.add_parser("check", help="Sanity-check a processed shot table (run this on real data)")
    k.add_argument("--shots", default="data/processed/shots.csv.gz")
    k.set_defaults(func=cmd_check)
    return p


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
