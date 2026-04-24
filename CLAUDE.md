# CAmap Nordic & Baltic — AI Agent Context

**last_verified:** 2026-04-24T13:00:00Z

## Project summary

Interactive map of TLS certificate authority (CA) sovereignty for Nordic and Baltic municipalities (FI, SE, NO, DK, EE, LV, LT). Surfaces kill-switch risk exposure: US-controlled CAs (CLOUD Act) vs EU / Nordic CAs.

**Live:** https://koldex.github.io/ca-sovereignty-map/
**Inspired by:** mxmap.ch (David Huser)

## Quick commands

```bash
uv sync --group dev                              # install dependencies
uv run python scripts/bootstrap_domains.py       # Phase 1: resolve domains (see caveat below)
uv run scan-certs --skip-ct --concurrency 30     # Phase 2: TLS scan
uv run analyze                                   # Phase 3: statistics
uv run pytest --cov                              # run tests
uv run ruff check src tests && uv run ruff format src tests  # lint/format
uv run python scripts/generate_topojson.py       # regenerate TopoJSON (default: no simplify)
```

## Architecture

Pipeline: **bootstrap_domains.py → scan-certs → data.json / data.min.json → GitHub Pages**

Key modules:
- `tls.py` — asyncio SSL scanner (primary), www fallback, no OpenSSL subprocess
- `dns.py` — DNS lookup with Quad9 / Cloudflare fallback (`dns.resolver.NXDOMAIN`, not `dns.exception.NXDOMAIN`)
- `signatures.py` — CA fingerprint database (~18 CAs, pattern-matched)
- `classifier.py` — weighted evidence aggregation, confidence scoring
- `pipeline.py` — `scan_many()` with semaphore (concurrency 50), builds data.json
- `resolve.py` — domain guessing + Wikidata SPARQL (User-Agent required)
- `scripts/bootstrap_domains.py` — Phase 1 entry point
- `scripts/generate_topojson.py` — GISCO LAU 2021 → topojson converter

## Data sources

- **Municipality boundaries:** Eurostat GISCO LAU 2021 (CC BY 4.0), cached at `.data_cache/`
- **Municipality domains:** Wikidata SPARQL → domain guessing → DNS validation
- **CA jurisdiction:** CCADB (Mozilla / Linux Foundation)
- **CT logs:** crt.sh API (optional, `--skip-ct` disables)

## Municipality ID format

`{COUNTRY}-{LAU_ID}` — matches GISCO LAU 2021 GISCO_ID with `_` → `-`.
Examples: `FI-049` (Espoo), `SE-0180` (Stockholm), `NO-0301` (Oslo), `DK-101` (Copenhagen).

For DK specifically, IDs match Danmarks Statistik's LAU codes exactly (98 kommuner + Christiansø = 99).

## Key pitfalls (must-read before changing the pipeline)

### 1. Nightly workflow skips Phase 1 (open: #19)

`.github/workflows/nightly.yml` only invokes `scan-certs`. It does **not** run `bootstrap_domains.py`. Consequence: any change to `overrides.json` is a no-op on the live map unless `municipality_domains.json` is also updated in the same PR.

Workaround until #19 is fixed: when adding an override, use a targeted merge of `overrides.json` into `municipality_domains.json` rather than a full `bootstrap_domains.py` regen (see PR #20 for the pattern). A blind full regen currently drops 243 working EE/LT/LV/NO entries because their Wikidata SPARQL rows have gone empty upstream.

### 2. Topojson simplification is destructive with `-P` mode (fixed: #23)

`scripts/generate_topojson.py` previously called `toposimplify -P 0.001`. The proportion-based mode retains 0.1 % of points regardless of source polygon size, which collapsed small kommuner (Bornholm, Frederiksberg, Fanø, Dragør, Christiansø, Langeland, Ærø, …) to 2-point line segments — invisible on the rendered map.

As of #23 the default path is `topoquantize 1e6` only (no simplification). Optional shape-preserving `-s` (spherical-area) mode is available via `--simplification <float>` but the default behaviour is safe. The script hard-fails at generation time if any regenerated DK polygon drops below 10 points.

### 3. Some Danish apex domains geo-block international traffic

`ringsted.dk` and at least a handful of other DK kommune apex hosts silently drop TCP:443 SYNs from non-DK networks. DNS resolves normally; `nc -z` and `curl --max-time 60` both time out from Finland and from Azure US West. The scanner cannot reach them regardless of timeout or concurrency settings.

Workaround: use a subdomain hosted on a different IP. For DK-329 the override is `selvbetjening.ringsted.dk`, which serves the same wildcard `*.ringsted.dk` certificate. Subdomains on shared hosting platforms (agendapublication.dk, os2faktor.dk, Semaphor) are usually reachable.

### 4. `dns.resolver.NXDOMAIN` vs `dns.exception.NXDOMAIN`

Use the first. The second exists but is the wrong exception class and caused 821 silent DNS failures in the original scanner.

## Data-integrity invariants (check these before accepting an override PR)

1. Every ID in `overrides.json` exists in `nordic-municipalities.topojson` (cross-reference script: `scripts/bootstrap_domains.py` at load time).
2. Every ID in the topojson has a matching entry in `data.min.json` (frontend lookup in `index.html:77`).
3. Every polygon in `nordic-municipalities.topojson` has ≥ 10 points (enforced at generation time in `scripts/generate_topojson.py`).
4. For DK specifically, IDs match the Danmarks Statistik kommune list (98 kommuner + Christiansø).

## Recent bug fixes

1. `dns.py`: `dns.resolver.NXDOMAIN` (was causing 821 failures in resolver)
2. `tls.py`: replaced OpenSSL subprocess with asyncio SSL (was causing 372 timeouts)
3. `index.html`: Leaflet JS SRI hash corrected
4. `data.min.json`: removed from `.gitignore` (required by GitHub Pages)
5. PRs #14 / #16 / #18 / #20 / #21: DK and SE override additions + municipality_domains sync
6. PR #23: topojson over-simplification fix — all polygons ≥ 10 points, 198 previously-invisible geometries restored
