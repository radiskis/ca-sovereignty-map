#!/usr/bin/env python3
"""Generate nordic-municipalities.topojson from GISCO LAU 2021 data.

Downloads the Eurostat GISCO Local Administrative Units (LAU) dataset,
filters for FI + SE + NO + DK municipalities, normalizes property names
to match the cert_sovereignty pipeline ID format, and converts to TopoJSON.

ID format: {CNTR_CODE}-{LAU_ID}  e.g. "FI-049", "SE-0180", "NO-0301", "DK-101"
These match the GISCO GISCO_ID field with underscore replaced by hyphen.

Usage:
    uv run python scripts/generate_topojson.py [--output nordic-municipalities.topojson]

Requirements (auto-installed via npx):
    topojson-server  (geo2topo command)
    topojson-simplify (toposimplify + topoquantize commands)
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parent.parent
CACHE_DIR = ROOT / ".data_cache"
CACHE_DIR.mkdir(exist_ok=True)

# Eurostat GISCO Local Administrative Units 2021, 1:1M scale, WGS84
GISCO_URL = (
    "https://gisco-services.ec.europa.eu/distribution/v2/lau/geojson/LAU_RG_01M_2021_4326.geojson"
)
GISCO_CACHE = CACHE_DIR / "gisco_lau_2021.geojson"

# Countries to include
COUNTRIES = ["FI", "SE", "NO", "DK", "EE", "LV", "LT"]


# ── Download ──────────────────────────────────────────────────────────────────


def download_gisco(force: bool = False) -> Path:
    """Download GISCO LAU 2021 file (125MB), cached locally."""
    if GISCO_CACHE.exists() and not force:
        size_mb = GISCO_CACHE.stat().st_size / 1_000_000
        print(f"Using cached GISCO data: {GISCO_CACHE} ({size_mb:.0f}MB)")
        return GISCO_CACHE

    print("Downloading GISCO LAU 2021 (~125MB) from Eurostat...")
    print(f"  URL: {GISCO_URL}")
    print("  This may take 1-2 minutes...")

    try:
        urllib.request.urlretrieve(GISCO_URL, GISCO_CACHE)
        size_mb = GISCO_CACHE.stat().st_size / 1_000_000
        print(f"  Downloaded {size_mb:.0f}MB → {GISCO_CACHE}")
        return GISCO_CACHE
    except Exception as e:
        print(f"  ERROR: {e}", file=sys.stderr)
        if GISCO_CACHE.exists():
            GISCO_CACHE.unlink()
        sys.exit(1)


# ── Process ───────────────────────────────────────────────────────────────────


def load_and_filter(gisco_path: Path) -> dict:
    """Load GISCO GeoJSON and filter for Nordic countries."""
    print("Parsing GISCO data (~125MB JSON, takes a few seconds)...")
    with open(gisco_path, encoding="utf-8") as f:
        data = json.load(f)

    features = data.get("features", [])
    print(f"  Total features: {len(features):,}")

    # Filter for our countries
    nordic = [f for f in features if f["properties"].get("CNTR_CODE") in COUNTRIES]
    print(f"  Nordic municipalities: {len(nordic)}")
    for cc in COUNTRIES:
        count = sum(1 for f in nordic if f["properties"]["CNTR_CODE"] == cc)
        print(f"    {cc}: {count}")

    return nordic


def normalize_feature(feature: dict) -> dict:
    """Normalize a GISCO feature to the cert_sovereignty ID format.

    Adds:
      id: "{CNTR_CODE}-{LAU_ID}" e.g. "FI-049", "SE-0180"
      name: LAU_NAME
      country: CNTR_CODE
      population: POP_2021 (if available)
    """
    props = feature["properties"]
    cc = props.get("CNTR_CODE", "")
    lau_id = props.get("LAU_ID", "")

    # GISCO_ID is "FI_049" → our format is "FI-049"
    municipality_id = f"{cc}-{lau_id}"

    new_props = {
        "id": municipality_id,
        "municipal_code": lau_id,
        "name": props.get("LAU_NAME", ""),
        "country": cc,
        "population": int(props.get("POP_2021", 0) or 0),
        # Keep original for reference
        "gisco_id": props.get("GISCO_ID", ""),
    }

    return {
        "type": "Feature",
        "geometry": feature["geometry"],
        "properties": new_props,
    }


def build_geojson(features: list[dict]) -> dict:
    """Build a normalized GeoJSON FeatureCollection."""
    normalized = [normalize_feature(f) for f in features]
    return {
        "type": "FeatureCollection",
        "features": normalized,
    }


# ── TopoJSON conversion ───────────────────────────────────────────────────────


def run_cmd(cmd: list[str], input_data: str | None = None) -> str:
    """Run a shell command and return stdout."""
    result = subprocess.run(
        cmd,
        input=input_data,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        print(f"Command failed: {' '.join(cmd)}", file=sys.stderr)
        print(f"stderr: {result.stderr[:500]}", file=sys.stderr)
        sys.exit(1)
    return result.stdout


def convert_to_topojson(
    geojson_path: Path,
    output_path: Path,
    simplification: float | None = None,
) -> None:
    """Convert GeoJSON to TopoJSON using topojson-server npm packages.

    By default this skips ``toposimplify`` entirely and relies on
    ``topoquantize`` alone for the wire-size reduction. Previous versions of
    this script used ``toposimplify -P 0.001`` (retain 0.1 % of points),
    which collapsed small islands and enclaves (Bornholm, Frederiksberg,
    Fanø, Dragør, Christiansø, Langeland, Ærø, …) into 2- to 4-point
    "polygons" that could not render as filled areas on the map. See #22
    for the full analysis and point-count evidence.

    Trade-off: output grows from ~0.6 MB to ~1.9 MB. Over HTTP the asset is
    gzipped by GitHub Pages, which is still well within budget for a static
    map application.

    If you *do* need to simplify further (e.g. for a mobile build), pass a
    spherical-area threshold via ``simplification``. Values in the range
    ``1e-9`` – ``5e-9`` preserve all DK polygons at ≥ 10 points each; the
    legacy ``-P 0.001`` proportion mode is destructive for small polygons and
    should not be used here.
    """
    print("\nConverting to TopoJSON...")

    # Step 1: geo2topo (GeoJSON → TopoJSON)
    print("  Step 1/2: geo2topo (GeoJSON → TopoJSON)")
    topo = run_cmd(
        ["npx", "-y", "-p", "topojson-server", "geo2topo", f"municipalities={geojson_path}"]
    )

    # Optional: toposimplify (spherical-area mode — shape-preserving).
    # We intentionally avoid the `-P` (proportion) mode because it collapses
    # tiny polygons regardless of how many source points they started with.
    if simplification is not None and simplification > 0:
        print(f"  Step 2a/2: toposimplify -s {simplification}")
        topo = run_cmd(
            ["npx", "-y", "-p", "topojson-simplify", "toposimplify", "-s", str(simplification)],
            input_data=topo,
        )

    # Step 2b: topoquantize (reduce coordinate precision → smaller file)
    print("  Step 2b/2: topoquantize 1e6")
    topo = run_cmd(
        ["npx", "-y", "-p", "topojson-simplify", "topoquantize", "1e6"],
        input_data=topo,
    )

    # Write output
    output_path.write_text(topo, encoding="utf-8")
    size_kb = output_path.stat().st_size / 1024
    print(f"\n  Output: {output_path} ({size_kb:.0f}KB)")


def point_count_summary(topo: dict) -> dict[str, dict[str, float | int]]:
    """Return point-count stats by country for validation/reporting."""
    arcs = topo.get("arcs", [])
    geoms = topo.get("objects", {}).get("municipalities", {}).get("geometries", [])

    def arc_len(index: int) -> int:
        if index < 0:
            index = ~index
        return len(arcs[index])

    def geom_points(geom: dict) -> int:
        if geom.get("type") == "Polygon":
            return sum(arc_len(idx) for ring in geom.get("arcs", []) for idx in ring)
        if geom.get("type") == "MultiPolygon":
            return sum(
                arc_len(idx) for poly in geom.get("arcs", []) for ring in poly for idx in ring
            )
        return 0

    by_country: dict[str, list[int]] = {}
    for geom in geoms:
        country = geom.get("properties", {}).get("country", "?")
        by_country.setdefault(country, []).append(geom_points(geom))

    summary: dict[str, dict[str, float | int]] = {}
    for country, counts in by_country.items():
        summary[country] = {
            "n": len(counts),
            "min": min(counts) if counts else 0,
            "avg": (sum(counts) / len(counts)) if counts else 0.0,
            "max": max(counts) if counts else 0,
            "under_10": sum(1 for c in counts if c < 10),
            "under_20": sum(1 for c in counts if c < 20),
        }
    return summary


# ── Main ──────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate nordic-municipalities.topojson")
    parser.add_argument(
        "--output",
        default=str(ROOT / "nordic-municipalities.topojson"),
        help="Output TopoJSON file path",
    )
    parser.add_argument(
        "--geojson-only",
        action="store_true",
        help="Only generate GeoJSON (skip TopoJSON conversion)",
    )
    parser.add_argument(
        "--force-download",
        action="store_true",
        help="Force re-download of GISCO data even if cached",
    )
    parser.add_argument(
        "--simplification",
        type=float,
        default=0.0,
        help=(
            "Optional spherical-area threshold passed to `toposimplify -s`. "
            "Default: 0.0 (skip simplification entirely; only quantize). "
            "Do NOT use the old proportion mode `-P 0.001` — it destroys small polygons."
        ),
    )
    args = parser.parse_args()

    output_path = Path(args.output)

    print("=" * 60)
    print("CAmap Nordics — Municipality Boundary Generator")
    print("=" * 60)
    print(f"Countries: {', '.join(COUNTRIES)}")
    print("Source:    Eurostat GISCO LAU 2021 (open data)")
    print("License:   CC BY 4.0 (Eurostat)")
    print(f"Output:    {output_path}")
    print()

    # Step 1: Download GISCO
    gisco_path = download_gisco(force=args.force_download)

    # Step 2: Filter and normalize
    nordic_features = load_and_filter(gisco_path)
    geojson = build_geojson(nordic_features)

    # Step 3: Write intermediate GeoJSON
    geojson_path = CACHE_DIR / "nordic_municipalities.geojson"
    with open(geojson_path, "w", encoding="utf-8") as f:
        json.dump(geojson, f, ensure_ascii=False, separators=(",", ":"))
    size_mb = geojson_path.stat().st_size / 1_000_000
    print(f"\nWrote intermediate GeoJSON: {geojson_path} ({size_mb:.1f}MB)")

    if args.geojson_only:
        print("\nDone (--geojson-only mode)")
        return

    # Step 4: Convert to TopoJSON
    simplify = args.simplification if args.simplification > 0 else None
    convert_to_topojson(geojson_path, output_path, simplification=simplify)

    # Step 5: Validate
    print("\nValidating output...")
    with open(output_path) as f:
        topo = json.load(f)
    objects = list(topo.get("objects", {}).keys())
    arcs = len(topo.get("arcs", []))
    print(f"  Objects: {objects}")
    print(f"  Arcs: {arcs:,}")

    # Count features per country
    geoms = topo["objects"].get("municipalities", {}).get("geometries", [])
    print(f"  Total geometries: {len(geoms)}")
    country_counts: dict[str, int] = {}
    for g in geoms:
        country = g.get("properties", {}).get("country", "?")
        country_counts[country] = country_counts.get(country, 0) + 1
    for cc in sorted(country_counts):
        print(f"    {cc}: {country_counts[cc]}")

    print("\nPoint-count validation (lower is worse; < 10 often means a visibly broken polygon):")
    point_stats = point_count_summary(topo)
    print(f"  {'country':8} {'n':5} {'min':6} {'avg':8} {'max':6} {'<10':5} {'<20':5}")
    for cc in sorted(point_stats):
        s = point_stats[cc]
        print(
            f"  {cc:8} {s['n']:5} {s['min']:6} {s['avg']:8.1f} {s['max']:6} "
            f"{s['under_10']:5} {s['under_20']:5}"
        )

    # Hard fail if any DK polygon still has < 10 points. Denmark's islands and
    # enclaves are the most visually obvious regressions, and this threshold
    # catches the specific failure mode that prompted #22.
    dk_stats = point_stats.get("DK")
    if dk_stats and dk_stats["under_10"] > 0:
        print(
            "\nERROR: DK polygons still contain < 10-point geometries. "
            "This output would visibly regress the frontend map.",
            file=sys.stderr,
        )
        sys.exit(1)

    print("\n" + "=" * 60)
    print("✓ nordic-municipalities.topojson generated successfully")
    print()
    print("Next steps:")
    print("  1. Run: uv run resolve-domains")
    print("  2. Run: uv run scan-certs --skip-ct")
    print("  3. Commit data: git add data.json data.min.json nordic-municipalities.topojson")
    print("=" * 60)


if __name__ == "__main__":
    main()
