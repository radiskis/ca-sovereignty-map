<!-- Thanks for contributing! Please read CONTRIBUTING.md before opening a PR. -->

## What does this PR do?

<!-- One or two sentences describing the change. -->

## Why?

<!-- Link to an issue, or explain the motivation. -->

## How was this verified?

<!-- Commands you ran, domains you checked with curl/openssl, screenshots, etc.
     For override changes, include the curl/openssl output that confirmed the
     new domain. -->

## Checklist

- [ ] `uv run ruff format src tests` is clean
- [ ] `uv run ruff check src tests` passes
- [ ] `uv run mypy src/cert_sovereignty` passes
- [ ] `uv run pytest --cov` passes
- [ ] New code has test coverage
- [ ] Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/)
- [ ] All commits are signed

## For override / signature / classifier changes

- [ ] Municipality ID matches `nordic-municipalities.topojson`
- [ ] Domain verified with both `curl -I` (reachability) and `openssl s_client` (TLS/cert subject)
- [ ] `reason` field cites the verification steps taken
- [ ] No commercial `.no`/`.fi`/`.se`/`.dk` domains unless demonstrably authoritative

## For pipeline / scanner changes

- [ ] Unit tests cover happy path and failure modes
- [ ] No new network calls outside of the scan pipeline
- [ ] Module docstring updated if recovery/enrichment chain changed
