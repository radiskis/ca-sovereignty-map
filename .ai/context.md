# CAmap Nordics — Session Memory

**last_verified:** 2026-04-24T13:00:00Z
**phase:** Post-#23 — boundary geometry, overrides and pipeline-sync all stabilised; one open issue (#19) remains.

## Handoff summary (most recent session: 2026-04-21 → 2026-04-23)

Triggered by issue #15 (tlk, Danish contributor) reporting missing Danish municipalities on the live map. The investigation cascaded through five override/pipeline PRs and one root-cause boundary-geometry PR:

- #14 (merged) — 10 DK domain overrides (6 previously absent, 4 wrong guesses). Authored by `tlk`; verification pass done retroactively by `koldex`.
- #16 (merged, closed #15) — 3 DK overrides for `unknown`-category kommuner: Dragør → `dragoer.dk`, Fanø → `fanoe.dk`, Ringkøbing-Skjern → `rksk.dk`. `_todo_DK-329` added for Ringsted.
- #17 (closed by #18) — Swedish equivalent of #15; 14 SE kommuner white or unknown.
- #18 (merged, closed #17) — 12 SE overrides. After local scan: 290/290 classified, 0 unknown.
- #19 (open) — **Nightly workflow skips Phase 1.** Exposed when the morning-after nightly still showed the old domains. Every override PR before #20 was a no-op on the live map.
- #20 (merged, partial fix for #19) — Synchronised `municipality_domains.json` with accumulated overrides via a targeted merge (not a full `bootstrap_domains.py` regen, because SPARQL drops 243 Baltic entries).
- #21 (merged) — DK-329 Ringsted resolved via `selvbetjening.ringsted.dk`. Apex `ringsted.dk` is geo-blocked at TCP:443 to non-DK networks.
- #22 (closed by #23) — Topojson geometry over-simplified. Every DK polygon had < 40 points, 5 had only 2–4 points (invisible line segments).
- #23 (merged, closed #22) — Regenerated topojson without destructive simplification. All DK/NO/LV polygons now ≥ 10 points. File size 0.6 MB → 1.9 MB on disk (~680 KB gzipped).

## Post-chain courtesy comment

Posted on issue #15 after merge of #23: short thank-you to `tlk` framed in the sovereignty context, including subtle Danish linguistic cues. No co-author attribution (per user request).

## Key facts to carry forward

- **DK kommune count:** 99 (98 DST kommuner + Christiansø). Fully covered after #23.
- **Topojson size:** 1.9 MB on disk, ~680 KB wire (gzipped by GitHub Pages).
- **`municipality_domains.json`:** 1 279 entries, 319 overrides.
- **Test suite:** 91 tests, all passing.

## Open problems waiting for attention

1. **#19 — Phase 1 not wired into nightly workflow.** Blocker for auto-propagation of override PRs. Root cause: `bootstrap_domains.py` currently produces regressions when Wikidata SPARQL returns fewer rows than the committed baseline (243 EE/LT/LV/NO entries affected at the time of investigation).
2. **SE-0617 Gnosjö and SE-2084 Avesta** — classify correctly when the apex responds but intermittently time out from the CI network. Candidate for a scanner `--retry` flag.
3. **No commit-time check on topojson polygon point counts.** #23 enforces the floor at *generation* time but not at *commit* time — someone editing the file by hand could regress without CI catching it.

## Conventions established

- **Override PRs**: must include both `overrides.json` and `municipality_domains.json` until #19 lands. See PR #20 for the targeted-merge pattern.
- **Override verification**: `curl -I` + `openssl s_client` per CONTRIBUTING.md. The `reason` field must cite HTTP status + cert CN + issuer. Safari-only verification is not sufficient — this was the finding that prompted the review of #14.
- **Commit messages**: Conventional Commits with country scope (`fix(DK): ...`, `fix(SE): ...`, `fix(pipeline): ...`). Signed commits mandatory (`required_signatures` branch protection rule on main).
- **CI-scoped preflight**: `ruff check src tests` + `ruff format --check src tests` + `mypy src/cert_sovereignty` + `pytest --cov` must all pass. Scripts under `scripts/` are not in the CI scope (but still should build clean).

## Pointers to in-session artefacts

- Targeted-merge script template: `/tmp/apply_overrides.py` (see PR #20 body for the logic; not committed to the repo).
- DST cross-reference helper: `/tmp/dst_check.py` (see issue #22 body and PR #21).
- Per-polygon point-count audit: `scripts/generate_topojson.py` now exposes `point_count_summary()` publicly.
