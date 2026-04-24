# CAmap Nordic & Baltic — Todo List

## Completed (most recent first)

### 2026-04-23
- PR #23 merged: regenerated `nordic-municipalities.topojson` without destructive simplification, closed #22.
- PR #21 merged: DK-329 Ringsted override → `selvbetjening.ringsted.dk` (apex is geo-blocked at TCP:443).
- PR #20 merged: synchronised `municipality_domains.json` with accumulated overrides. Partial fix for #19.
- Posted courtesy comment on closed issue #15 thanking contributor `tlk` for the report that started the investigation.

### 2026-04-22
- Issue #22 opened documenting topojson over-simplification root cause (all DK polygons < 40 points, 5 at 2–4 points).
- Issue #19 opened documenting nightly workflow's Phase 1 skip.
- Investigated geo-blocking on `ringsted.dk`; identified `selvbetjening.ringsted.dk` as reachable subdomain with wildcard `*.ringsted.dk` cert.
- Two manual nightly dispatches done during the investigation.

### 2026-04-21
- PR #18 merged: 12 SE overrides. Closed #17. Local scan: 290/290 SE classified, 0 unknown.
- PR #16 merged: 3 more DK overrides (Dragør, Fanø, Ringkøbing-Skjern). Closed #15 (note: later re-investigated for completeness).
- PR #14 merged: 10 DK overrides from contributor `tlk`, after retroactive `curl` + `openssl` verification pass and a squash-merge with country-scoped Conventional Commit.
- Issue #17 opened for Swedish equivalent of #15.

## Pending (rough priority order)

1. **Resolve #19** — make `bootstrap_domains.py` resilient to transient Wikidata SPARQL empty results for EE/LT/LV/NO, then wire Phase 1 into `.github/workflows/nightly.yml` so override PRs propagate automatically to the live map.
2. **Add a commit-time point-count guard** — CI check or pre-commit hook that fails if any polygon in the committed `nordic-municipalities.topojson` has < 10 points. The generator (#23) enforces it only at generation time.
3. **Scanner `--retry` flag** — re-attempts on timeouts would likely resolve SE-0617 Gnosjö and SE-2084 Avesta, currently `unknown` in live data due to intermittent CI-side timeouts. Apex domains scan fine from Nordic networks.
4. **Consider repo-level documentation of the override workflow** — the in-repo `CONTRIBUTING.md` §"Adding or fixing overrides" still implicitly assumes Phase 1 runs in CI. Either update that section to describe the current dual-update requirement, or leave it alone and resolve #19 first.

## Deferred / out of scope

- Adding Iceland (IS) municipalities. Mentioned in earlier notes; no blocker but no demand either.
- Replacing `topojson-simplify` with a Python-native simplifier to drop the `npx` dependency from topojson regeneration. Low value; current tooling works.

## Audit checklist when reviewing override PRs

1. Every new ID exists in `nordic-municipalities.topojson`.
2. Domain verified with `curl -I` **and** `openssl s_client`; verification evidence cited in the `reason` field.
3. `municipality_domains.json` is updated in the same PR (until #19 is fixed).
4. `overrides.json` has no duplicate IDs; trailing comma still absent.
5. `uv run ruff check src tests` + `mypy src/cert_sovereignty` + `pytest -x --no-cov` pass locally.
6. Commit messages follow Conventional Commits with country scope; commits signed.
