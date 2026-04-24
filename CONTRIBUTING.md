# Contributing to ca-sovereignty-map

Thanks for your interest in improving the CA sovereignty map of Nordic and
Baltic municipalities. This document covers the practical steps; see
[`docs/branching.md`](docs/branching.md) for the Git workflow and
[`SECURITY.md`](SECURITY.md) for how to report vulnerabilities privately.

## Ways to contribute

The most useful contributions usually fall into one of these buckets:

1. **Fix a wrong municipality domain.** Open a PR that edits
   [`overrides.json`](overrides.json) with a verified domain and a short
   reason. See [Adding or fixing overrides](#adding-or-fixing-overrides).
2. **Add a new CA signature.** Edit
   [`src/cert_sovereignty/signatures.py`](src/cert_sovereignty/signatures.py)
   with issuer patterns, jurisdiction, and a test fixture.
3. **Improve the scan pipeline.** Changes to `tls.py`, `resolve.py`,
   `classifier.py` etc. must ship with unit tests.
4. **Documentation, methodology, tests.** Always welcome.

## Development setup

Prerequisites: Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/koldex/ca-sovereignty-map.git
cd ca-sovereignty-map
uv sync --group dev
```

### Everyday commands

```bash
# Auto-format (must be clean before pushing — CI enforces this)
uv run ruff format src tests

# Lint
uv run ruff check src tests

# Type check
uv run mypy src/cert_sovereignty

# Run the full test suite with coverage
uv run pytest --cov

# Fast test run (no coverage)
uv run pytest
```

### Pipeline commands

```bash
uv run python scripts/bootstrap_domains.py   # Phase 1: resolve domains
uv run scan-certs --skip-ct --concurrency 30 # Phase 2: TLS scan
uv run analyze                               # Phase 3: statistics
```

## Adding or fixing overrides

Every override in [`overrides.json`](overrides.json) must:

1. **Target a real municipality ID** in the format `{COUNTRY}-{LAU_ID}`
   (e.g. `NO-3422`, `FI-091`). Verify the ID against
   [`nordic-municipalities.topojson`](nordic-municipalities.topojson).
2. **Point to a domain verified with `curl` and `openssl`** before the PR is
   opened. The reason field should cite what you checked:

   ```json
   "NO-3422": {
     "domain": "amot.kommune.no",
     "reason": "www.amot.no times out; amot.kommune.no 301→www, Let's Encrypt R12 verified"
   }
   ```

3. **Exclude commercial `.no`/`.fi`/etc. domains** that happen to resolve.
   Norwegian municipalities should generally use `{slug}.kommune.no` unless
   a `.no` domain is demonstrably authoritative.
4. **Include a matching update to `municipality_domains.json`** in the same
   PR. The nightly workflow currently only runs Phase 2 of the pipeline
   (`scan-certs`), not Phase 1 (`bootstrap_domains.py`), so changes to
   `overrides.json` alone do not reach the live map. Use a targeted merge
   (update an existing record's `domain` + `domain_source: "override"`, or
   append a new record populated from the topojson); do **not** run a full
   `bootstrap_domains.py` regen unless you know Wikidata is currently
   returning complete results for every Baltic country, which it often
   isn't. See [#19](https://github.com/koldex/ca-sovereignty-map/issues/19)
   for the tracking issue and PR [#20](https://github.com/koldex/ca-sovereignty-map/pull/20)
   for a worked example of the targeted-merge pattern.

## Pull request checklist

Before opening a PR, confirm:

- [ ] `uv run ruff format src tests` is clean
- [ ] `uv run ruff check src tests` passes
- [ ] `uv run mypy src/cert_sovereignty` passes
- [ ] `uv run pytest --cov` passes with coverage ≥ 55%
- [ ] New functionality has tests
- [ ] Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/)
- [ ] All commits are signed (see [signed commits docs](https://docs.github.com/authentication/managing-commit-signature-verification))

The PR template will remind you of this. CI will reject formatting or test
failures, and the ruleset on `main` requires all checks to pass before merge.

## Commit message conventions

We follow Conventional Commits. Examples from the repo history:

- `fix(NO): harden domain validation and add .kommune.no fallback recovery`
- `test: add async tests for validation logic`
- `docs: explain confidence scoring methodology`
- `chore(actions): bump actions/checkout to v4.2.0`

Country-scoped changes use the ISO code (`NO`, `FI`, `SE`, `DK`, `EE`, `LV`,
`LT`) as the scope.

## Reporting bugs and requesting features

Use the issue templates at
<https://github.com/koldex/ca-sovereignty-map/issues/new/choose>. For
security-relevant issues see [`SECURITY.md`](SECURITY.md) — do not open a
public issue for those.

## Code of Conduct

This project follows the [Contributor Covenant](CODE_OF_CONDUCT.md). By
participating you agree to uphold it.

## License

By contributing you agree that your work will be licensed under the
[EUPL-1.2](LICENCE) — the same license as the rest of the project.
