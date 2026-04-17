# Branching workflow

`main` is a protected branch. All changes land through pull requests that pass
CI.

## Quick reference

```bash
# 1. Start a branch
git checkout main && git pull
git checkout -b feat/short-slug

# 2. Work, commit (signed), push
git add -A
git commit -m "feat(NO): add override for new municipality"
git push -u origin feat/short-slug

# 3. Open a PR
gh pr create --fill

# 4. Wait for CI (Lint & format, Tests & coverage)
# 5. Squash-merge when green
gh pr merge --squash --delete-branch
```

## Branch naming

Recommended prefixes:

- `feat/` — new functionality
- `fix/` — bug fixes
- `docs/` — documentation-only changes
- `refactor/` — code shape changes without behaviour change
- `test/` — tests only
- `chore/` — tooling, CI, dependencies
- `ci/` — CI workflow changes

Not currently enforced, but consistent names make the branch list scannable.

## Commit messages

We use [Conventional Commits](https://www.conventionalcommits.org/). Examples
from the repo history:

- `fix(NO): harden domain validation and add .kommune.no fallback recovery`
- `test: add async tests for NO validation hardening`
- `style: apply ruff formatting to test files`

Scopes (`NO`, `FI`, `SE`, ...) are country codes where relevant.

Every commit must be signed. If you use the 1Password SSH agent, Git signing
happens automatically; otherwise see
[GitHub's signed commits documentation](https://docs.github.com/authentication/managing-commit-signature-verification).

## Active protections on `main`

Defined in [`.github/rulesets/main-protection.json`](../.github/rulesets/main-protection.json):

- No force pushes
- No deletion
- Linear history (squash or rebase merges only, no merge commits)
- Signed commits required
- All changes must arrive via PR
- CI jobs `Lint & format` and `Tests & coverage` must pass before merge

## Emergency bypass

Repository admins can bypass the ruleset from Settings → Rules → Rulesets →
"Protect main branch" → "Bypass" for urgent fixes. The bypass is logged in
the repository's rule insights. Prefer to land fixes through a PR whenever
possible, even for small hotfixes; admin bypass should be reserved for
incidents where CI itself is broken and the fix is obviously safe.

## Pre-flight checks

Run these locally before pushing to avoid CI round-trips:

```bash
uv run ruff format src tests       # auto-fix formatting
uv run ruff check src tests        # lint
uv run mypy src/cert_sovereignty   # type check
uv run pytest --cov                # full suite with coverage
```

These mirror the CI jobs in `.github/workflows/ci.yml`.
