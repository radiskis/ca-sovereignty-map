# CAmap Nordic & Baltic — AI Session Context

**last_verified:** 2026-04-24T13:00:00Z
**project_version:** 0.1.x
**status:** Active — overrides pipeline and boundary geometry stabilised; one known CI gap open (#19)

## Current state

- **Municipality boundaries** (`nordic-municipalities.topojson`): 1 313 geometries across FI/SE/NO/DK/EE/LV/LT — regenerated without destructive simplification (PR #23). Every polygon now ≥ 10 points; 0.6 MB → 1.9 MB on disk, ~680 KB gzipped on the wire.
- **Municipality → domain map** (`municipality_domains.json`): 1 279 entries (FI 299 · NO 349 · SE 290 · LV 112 · DK 99 · EE 72 · LT 58). 319 carry `"domain_source": "override"`.
- **Live scan results** (`data.min.json`): deployed via nightly GitHub Actions workflow to `https://koldex.github.io/ca-sovereignty-map/`.
- **DK coverage (post-fix)**: 99 / 99 kommuner with valid renderable geometry. 98 classified at ≥ 75 % confidence; DK-329 Ringsted resolved via `selvbetjening.ringsted.dk` because the apex `ringsted.dk` is geo-blocked to non-DK traffic at TCP:443.
- **SE coverage (post-fix)**: 290 / 290 kommuner; after overrides from #18, local scan returns 0 `unknown`.

## Recent session: issue #15 → #22 investigation chain (2026-04-21 → 2026-04-23)

What looked like a single "missing Danish municipality" bug unrolled through five PRs of symptom-fixing and one root-cause fix:

| PR | Scope | Closes |
|---|---|---|
| #14 | 10 DK overrides (6 previously absent from data, 4 wrong-domain) | contributor: `tlk` |
| #16 | 3 DK overrides + `_todo_DK-329` (Dragør, Fanø, Ringkøbing-Skjern) | #15 |
| #18 | 12 SE overrides for missing / unknown kommuner | #17 |
| #20 | **Sync `municipality_domains.json`** — exposed that the nightly never invokes Phase 1 | #19 (partial) |
| #21 | DK-329 Ringsted via `selvbetjening.ringsted.dk` (wildcard `*.ringsted.dk` cert) | (#15 tail) |
| #23 | **Topojson regeneration** — replaced destructive `toposimplify -P 0.001` with quantize-only default | #22 |

## Open issues

- **#19** — Nightly workflow skips Phase 1 (`scripts/bootstrap_domains.py`). Any future override PR must include a targeted `municipality_domains.json` update or it will not reach the live map. Blocked on making `bootstrap_domains.py` resilient to transient Wikidata SPARQL dropouts: current full regen drops 243 EE/LT/LV/NO entries whose SPARQL rows have gone empty upstream.

## Pending tasks for next session

1. Resolve #19 — harden `bootstrap_domains.py` so Phase 1 can run in CI without regressing existing overrides (preserve committed baseline when SPARQL returns empty for a country; treat the file as a merge source, not a replace target).
2. Once #19 lands, add `uv run python scripts/bootstrap_domains.py` as a pre-step in `.github/workflows/nightly.yml` so future override PRs propagate automatically.
3. Investigate SE-0617 Gnosjö and SE-2084 Avesta — classify correctly when the apex responds, but intermittently time out from Azure US West. Consider a `--retry` flag for `scan-certs`.
4. Consider a repo-level check that fails CI if any committed polygon in `nordic-municipalities.topojson` drops below 10 points. The generator already enforces this at generation time (PR #23); a commit-time guard would catch accidental downgrades of the tracked file.

## Architecture decisions log

| Date | Decision | Reason |
|------|----------|--------|
| 2026-03-24 | asyncio SSL as primary TLS scanner | OpenSSL subprocess timed out for 372/884 domains |
| 2026-03-24 | www fallback in scanner | ~10 % of certs live only on the www subdomain |
| 2026-03-24 | GISCO LAU 2021 for boundaries | Single authoritative source for FI + SE + NO + DK + EE + LV + LT |
| 2026-04-21 | Targeted `municipality_domains.json` merge instead of full `bootstrap_domains.py` regen | Wikidata SPARQL returns fewer entries than the committed baseline for Baltic countries; full regen would regress 243 working entries |
| 2026-04-22 | Drop `toposimplify -P` entirely; default to `topoquantize 1e6` + optional `-s` (area-weighted) | Proportion-based simplification collapses small polygons to 2-point lines; island and enclave kommuner became invisible on the map |
| 2026-04-22 | Hard floor on polygon point count in `generate_topojson.py` | Catches future regressions of the `-P 0.001` failure mode at generation time |

## Pipeline caveat (important)

`scripts/bootstrap_domains.py` is **not** currently invoked by `.github/workflows/nightly.yml`. The deployed map uses whatever is committed to `municipality_domains.json`. Override PRs therefore must include a matching `municipality_domains.json` update alongside `overrides.json` until #19 is resolved. PR #20 introduced a repeatable targeted-update pattern that preserves every existing record and only diffs entries referenced by `overrides.json`.

## AI Agent Sync

- Last Warp AI update: 2026-04-24T13:00:00Z
- Related files: `CLAUDE.md`, `.ai/context.md`, `todo_list.md`
- Cross-references: `CONTRIBUTING.md` §"Adding or fixing overrides" remains the single source of truth for contributor workflow; this file is for agent context only.
