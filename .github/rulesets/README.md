# Committed branch rulesets

This directory holds branch/tag rulesets as JSON so that repository protection
is version-controlled, auditable, and reviewable in pull requests.

## Source of truth

The JSON files in this directory are the canonical source. If you change a
ruleset in the GitHub UI, re-export it (Settings → Rules → Rulesets → the
ruleset → "Export") and commit the updated JSON. CI does **not** yet
auto-apply changes; see "Applying" below.

## Applying

Apply a ruleset to the repository with the GitHub REST API. Requires a token
with the `repo` scope (the `gh` CLI default is fine):

```bash
# Create a new ruleset
gh api -X POST \
  /repos/koldex/ca-sovereignty-map/rulesets \
  --input .github/rulesets/main-protection.json
```

To update an existing ruleset, first find its ID:

```bash
gh api /repos/koldex/ca-sovereignty-map/rulesets \
  --jq '.[] | {id, name}'
```

Then:

```bash
RULESET_ID=<id>
gh api -X PUT \
  /repos/koldex/ca-sovereignty-map/rulesets/$RULESET_ID \
  --input .github/rulesets/main-protection.json
```

## What `main-protection.json` does

Rules applied to the default branch (`main`):

| Rule                       | Effect                                                                 |
| -------------------------- | ---------------------------------------------------------------------- |
| `deletion`                 | Block deletion of `main`                                               |
| `non_fast_forward`         | Block force pushes to `main`                                           |
| `required_linear_history`  | Reject merge commits — enforces squash/rebase workflow                 |
| `required_signatures`      | Reject unsigned commits — requires GPG/SSH-signed commits              |
| `pull_request`             | All changes must arrive via PR; merge methods limited to squash/rebase |
| `required_status_checks`   | `CI / Lint & format` and `CI / Tests & coverage` must pass             |

The bypass list is empty; repository admins can still bypass via the Settings
UI in emergencies. See [`docs/branching.md`](../../docs/branching.md) for the
contributor workflow.
