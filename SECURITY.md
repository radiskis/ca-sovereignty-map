# Security Policy

## Scope

`ca-sovereignty-map` is a public, read-only observation tool that scans
publicly-reachable TLS endpoints of Nordic and Baltic municipal websites and
classifies the certificate authority serving each. It does not accept user
input, does not store credentials, and does not transmit data on behalf of
third parties. Nevertheless, as a project in the TLS/CA security space, we
take vulnerability reports seriously.

This policy covers:

- The Python scanning pipeline (`src/cert_sovereignty/`)
- The static frontend served at <https://koldex.github.io/ca-sovereignty-map/>
- The build and deploy workflows in `.github/workflows/`
- The committed data artifacts (`data.json`, `data.min.json`,
  `nordic-municipalities.topojson`)

This policy does **not** cover:

- Third-party CAs, root stores, or municipality websites themselves. If you
  discover a genuine issue with a municipality's TLS configuration, please
  report it directly to that municipality's IT contact.
- The CCADB dataset, which is operated by the CA/Browser Forum.

## Reporting a vulnerability

**Please do not open a public GitHub issue for security vulnerabilities.**

Use GitHub's private vulnerability reporting feature:

1. Go to <https://github.com/koldex/ca-sovereignty-map/security/advisories/new>
2. Describe the issue, reproduction steps, and impact
3. Submit — only repository maintainers will see the advisory

Alternatively, open a draft security advisory via
`Security` → `Advisories` → `New draft security advisory` on GitHub.

### What to include

- A clear description of the issue
- Steps or a proof-of-concept to reproduce
- The affected component (file path, function, workflow, URL)
- Your assessment of the impact
- Any suggested remediation

### What to expect

- Acknowledgement within 7 days
- A triage decision within 14 days (accept, needs-more-info, or reject)
- A coordinated fix and disclosure timeline if the report is accepted
- Credit in the release notes unless you prefer to remain anonymous

## Supported versions

This project deploys continuously from `main`; there are no tagged releases at
present. The live site at <https://koldex.github.io/ca-sovereignty-map/>
always reflects the latest `main` commit. Security fixes are applied directly
to `main` through the normal PR flow.

## Security-related enabled features

The following GitHub-native security features are enabled on the repository:

- **Private vulnerability reporting** — the preferred disclosure channel above
- **Secret scanning with push protection** — blocks commits that contain
  recognised secret patterns
- **Dependabot alerts** — monitors dependencies for known CVEs
- **Dependabot version updates** — weekly PRs for GitHub Actions
  (`.github/dependabot.yml`)
- **Branch ruleset on `main`** requiring signed commits, linear history, and
  passing CI before merge (`.github/rulesets/main-protection.json`)

## Hall of fame

Researchers who have responsibly reported issues will be listed here after
coordinated disclosure.
