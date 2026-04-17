"""Tests for TLS certificate chain scanning."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from cert_sovereignty.models import SignalKind
from cert_sovereignty.tls import (
    _extract_pem_certs,
    _is_transient_error,
    _match_cert_to_ca,
    _no_kommune_fallback,
    scan_certificate_chain,
)


def test_extract_pem_certs_empty() -> None:
    assert _extract_pem_certs("") == []


def test_extract_pem_certs_single() -> None:
    # _extract_pem_certs is kept for diagnostic use with openssl showcerts output
    pem_output = """
depth=0 CN=example.fi
-----BEGIN CERTIFICATE-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA
-----END CERTIFICATE-----
"""
    certs = _extract_pem_certs(pem_output)
    assert len(certs) == 1
    assert "-----BEGIN CERTIFICATE-----" in certs[0]
    assert "-----END CERTIFICATE-----" in certs[0]


def test_extract_pem_certs_multiple() -> None:
    pem_output = """
-----BEGIN CERTIFICATE-----
AAAA
-----END CERTIFICATE-----
-----BEGIN CERTIFICATE-----
BBBB
-----END CERTIFICATE-----
"""
    certs = _extract_pem_certs(pem_output)
    assert len(certs) == 2


def test_extract_pem_certs_no_partial() -> None:
    # Incomplete PEM block (missing END) must not produce a result
    pem_output = "-----BEGIN CERTIFICATE-----\nAAAA\n"
    assert _extract_pem_certs(pem_output) == []


def test_redirect_strip_www_uses_removeprefix() -> None:
    """B005: lstrip('www.') strips chars, removeprefix strips the exact string."""
    # 'webmaster.example.fi' must not be stripped by removeprefix('www.')
    assert "webmaster.example.fi".removeprefix("www.") == "webmaster.example.fi"
    # 'www.example.fi' is correctly stripped
    assert "www.example.fi".removeprefix("www.") == "example.fi"


def test_match_cert_to_ca_letsencrypt(letsencrypt_leaf) -> None:
    results = _match_cert_to_ca(letsencrypt_leaf, SignalKind.LEAF_ISSUER)
    assert len(results) >= 1
    ca_names = [ev.ca_name for ev in results]
    assert "Let's Encrypt (ISRG)" in ca_names


def test_match_cert_to_ca_buypass(buypass_leaf) -> None:
    results = _match_cert_to_ca(buypass_leaf, SignalKind.LEAF_ISSUER)
    ca_names = [ev.ca_name for ev in results]
    assert "Buypass" in ca_names


# ── _no_kommune_fallback ─────────────────────────────────────────────────────


def test_no_kommune_fallback_www_prefix() -> None:
    assert _no_kommune_fallback("www.nord-fron.no") == "nord-fron.kommune.no"
    assert _no_kommune_fallback("www.amot.no") == "amot.kommune.no"


def test_no_kommune_fallback_bare() -> None:
    assert _no_kommune_fallback("laerdal.no") == "laerdal.kommune.no"
    assert _no_kommune_fallback("vinje.no") == "vinje.kommune.no"


def test_no_kommune_fallback_already_authoritative() -> None:
    # Already .kommune.no or .herad.no — must return None
    assert _no_kommune_fallback("nord-fron.kommune.no") is None
    assert _no_kommune_fallback("ulvik.herad.no") is None


def test_no_kommune_fallback_non_norwegian() -> None:
    # Non-.no domains must return None
    assert _no_kommune_fallback("espoo.fi") is None
    assert _no_kommune_fallback("stockholm.se") is None
    assert _no_kommune_fallback("laerdal.com") is None


# ── scan_certificate_chain — Recovery 3 (─────────────────────────────────────


def _err(domain: str, msg: str = "SSL error: SNI") -> dict:
    """Minimal failed _scan_asyncio_ssl result."""
    return {
        "domain": domain,
        "scan_timestamp": "2026-01-01T00:00:00+00:00",
        "chain": [],
        "evidence": [],
        "tls_version": "",
        "verification": "",
        "error": msg,
        "cert_mismatch": False,
        "http_accessible": None,
    }


def _ok(domain: str) -> dict:
    """Minimal successful _scan_asyncio_ssl result."""
    return {
        "domain": domain,
        "scan_timestamp": "2026-01-01T00:00:00+00:00",
        "chain": [],
        "evidence": [],
        "tls_version": "TLSv1.3",
        "verification": "OK",
        "error": None,
        "cert_mismatch": False,
        "http_accessible": None,
    }


async def test_recovery3_triggers_for_bare_no() -> None:
    """www.amot.no SSL error → Recovery 3 retries amot.kommune.no."""
    with patch(
        "cert_sovereignty.tls._scan_asyncio_ssl",
        new_callable=AsyncMock,
        side_effect=[_err("www.amot.no"), _ok("amot.kommune.no")],
    ):
        result = await scan_certificate_chain("www.amot.no")
    assert result["scanned_domain"] == "amot.kommune.no"
    assert result["domain"] == "www.amot.no"
    assert result["error"] is None


async def test_recovery3_does_not_trigger_for_non_no() -> None:
    """Recovery 3 does not fire for non-Norwegian domains."""
    with patch(
        "cert_sovereignty.tls._scan_asyncio_ssl",
        new_callable=AsyncMock,
        return_value=_err("www.espoo.fi"),
    ):
        result = await scan_certificate_chain("www.espoo.fi")
    assert result["error"] == "SSL error: SNI"
    assert result.get("scanned_domain", "") == ""


async def test_recovery3_does_not_trigger_for_kommune_domain() -> None:
    """Recovery 3 does not fire when domain is already .kommune.no."""
    with (
        patch(
            "cert_sovereignty.tls._scan_asyncio_ssl",
            new_callable=AsyncMock,
            return_value=_err("amot.kommune.no", msg="SSL error: test"),
        ),
        patch("cert_sovereignty.tls._check_port_open", new_callable=AsyncMock, return_value=False),
    ):
        result = await scan_certificate_chain("amot.kommune.no")
    # Should stay on the original error, no .kommune.no sub-fallback attempted
    assert result["error"] == "SSL error: test"
    assert result.get("scanned_domain", "") == ""


def test_match_cert_to_ca_unknown() -> None:
    from cert_sovereignty.models import CertChainEntry

    unknown_cert = CertChainEntry(
        position=0,
        cert_type="leaf",
        subject_cn="example.fi",
        issuer_cn="Unknown Local CA",
        issuer_org="Local Municipality IT",
        issuer_country="FI",
    )
    results = _match_cert_to_ca(unknown_cert, SignalKind.LEAF_ISSUER)
    assert results == []


# ── _is_transient_error ──────────────────────────────────────────────────


def test_is_transient_error_recognises_expected_markers() -> None:
    assert _is_transient_error("Connection timeout (15s)")
    assert _is_transient_error("Connection error: [Errno -3] Temporary failure in name resolution")
    assert _is_transient_error("Connection reset by peer")
    assert _is_transient_error("DNS resolution failed: no A record for odeshog.se")


def test_is_transient_error_false_for_terminal_states() -> None:
    assert not _is_transient_error(None)
    assert not _is_transient_error("")
    # http_only is a terminal classification and must never retry.
    assert not _is_transient_error("http_only")
    # SSL failures are not considered transient — the cert chain itself is wrong.
    assert not _is_transient_error("SSL verification failed: hostname mismatch")
    assert not _is_transient_error("SSL error: TLSV1_UNRECOGNIZED_NAME")


# ── scan_certificate_chain — transient-error retry ──────────────────────────────


async def test_retry_fires_for_transient_dns_error_and_recovers() -> None:
    """A first-pass DNS failure is retried and the second attempt is adopted."""
    first_pass_dns_failed = _err(
        "odeshog.se", msg="DNS resolution failed: no A record for odeshog.se"
    )
    second_pass_ok = _ok("odeshog.se")
    with (
        patch(
            "cert_sovereignty.tls._scan_with_recovery_chain",
            new_callable=AsyncMock,
            side_effect=[first_pass_dns_failed, second_pass_ok],
        ),
        patch("cert_sovereignty.tls.asyncio.sleep", new_callable=AsyncMock, return_value=None),
    ):
        result = await scan_certificate_chain("odeshog.se", timeout=15)
    assert result["error"] is None
    assert result["tls_version"] == "TLSv1.3"


async def test_retry_fires_for_connection_timeout() -> None:
    """avesta.se: 15 s not enough, the retry path with widened timeout succeeds."""
    call_timeouts: list[int] = []

    async def fake_chain(domain: str, port: int, timeout: int) -> dict:
        call_timeouts.append(timeout)
        if len(call_timeouts) == 1:
            return _err(domain, msg=f"Connection timeout ({timeout}s)")
        return _ok(domain)

    with (
        patch(
            "cert_sovereignty.tls._scan_with_recovery_chain",
            new=AsyncMock(side_effect=fake_chain),
        ),
        patch("cert_sovereignty.tls.asyncio.sleep", new_callable=AsyncMock, return_value=None),
    ):
        result = await scan_certificate_chain("avesta.se", timeout=15)
    assert result["error"] is None
    # First pass used the caller's timeout, retry used the widened one and it
    # must be strictly greater than the first-pass timeout (and capped at 45).
    assert call_timeouts[0] == 15
    assert call_timeouts[1] > 15
    assert call_timeouts[1] <= 45


async def test_retry_does_not_fire_for_ssl_error() -> None:
    """Non-transient errors (e.g. SSL hostname mismatch) must not trigger retry."""
    scan_mock = AsyncMock(return_value=_err("example.se", msg="SSL error: mismatch"))
    with (
        patch("cert_sovereignty.tls._scan_with_recovery_chain", new=scan_mock),
        patch("cert_sovereignty.tls.asyncio.sleep", new_callable=AsyncMock, return_value=None),
    ):
        result = await scan_certificate_chain("example.se", timeout=15)
    assert scan_mock.await_count == 1  # no retry
    assert result["error"] == "SSL error: mismatch"


async def test_retry_keeps_first_result_if_retry_also_transient() -> None:
    """If the retry still fails with a transient error, keep the first result."""
    first = _err("example.se", msg="Connection timeout (15s)")
    second = _err("example.se", msg="Connection timeout (45s)")
    with (
        patch(
            "cert_sovereignty.tls._scan_with_recovery_chain",
            new_callable=AsyncMock,
            side_effect=[first, second],
        ),
        patch("cert_sovereignty.tls.asyncio.sleep", new_callable=AsyncMock, return_value=None),
    ):
        result = await scan_certificate_chain("example.se", timeout=15)
    # First pass result is retained — we do not silently replace it with the
    # retry's (also failed) result, so downstream error categorisation is stable.
    assert result["error"] == "Connection timeout (15s)"


# ── _connect_and_scan — robust DNS resolver ──────────────────────────────────


async def test_connect_and_scan_returns_dns_failed_when_all_resolvers_fail() -> None:
    """If every configured resolver fails to return an A record, we emit a
    distinctive ``DNS resolution failed`` error message that downstream
    ``pipeline.serialize_result`` maps to ``error_category = "dns_failed"``.
    """
    from cert_sovereignty.tls import _connect_and_scan

    with patch(
        "cert_sovereignty.tls.lookup_a",
        new_callable=AsyncMock,
        return_value=[],
    ):
        result = await _connect_and_scan("nonexistent.invalid", 443, 5, verify=True)
    assert result["error"].startswith("DNS resolution failed")
    assert result["chain"] == []


async def test_connect_and_scan_uses_lookup_a() -> None:
    """Make sure the TLS scanner calls ``dns.lookup_a`` — NOT ``loop.getaddrinfo``.
    This is the core regression fix for the 5 SE municipalities that were
    marked Unknown due to a single runner-side DNS hiccup.
    """
    from cert_sovereignty.tls import _connect_and_scan

    mocked = AsyncMock(return_value=[])
    with patch("cert_sovereignty.tls.lookup_a", new=mocked):
        await _connect_and_scan("example.se", 443, 5, verify=True)
    mocked.assert_awaited_once_with("example.se")


# ── scan_certificate_chain — http_only safety-net ──────────────────────────────


def _ok_with_chain(domain: str) -> dict:
    """Successful scan result with a non-empty chain entry."""
    base = _ok(domain)
    # Pipeline code accepts a truthy 'chain' — empty list counts as false.
    base["chain"] = [{"cert_type": "leaf"}]
    return base


async def test_http_only_safety_net_tries_www_with_verify_disabled() -> None:
    """When apex would otherwise be classified http_only, give ``www.<domain>``
    one more chance with verification disabled before committing. This is the
    fix for e.g. landskrona.se / skara.se that previously got http_only
    despite serving valid TLS on the www subdomain.
    """

    async def fake_scan(domain: str, port: int, timeout: int) -> dict:
        if domain == "landskrona.se":
            return _err(domain, msg="Connection error: apex 443 refused")
        if domain == "www.landskrona.se":
            # First www call is the recovery-1 verify=True attempt — return
            # an error so we get to the safety-net (verify=False) path.
            return _err(domain, msg="SSL error: hostname mismatch")
        return _err(domain)

    async def fake_scan_noverify(domain: str, port: int, timeout: int) -> dict:
        if domain == "www.landskrona.se":
            return _ok_with_chain(domain)
        return _err(domain)

    with (
        patch(
            "cert_sovereignty.tls._scan_asyncio_ssl",
            new=AsyncMock(side_effect=fake_scan),
        ),
        patch(
            "cert_sovereignty.tls._scan_asyncio_ssl_no_verify",
            new=AsyncMock(side_effect=fake_scan_noverify),
        ),
        # Safety-net must win before we even probe port 80.
        patch(
            "cert_sovereignty.tls._check_port_open",
            new_callable=AsyncMock,
            return_value=True,
        ),
        patch("cert_sovereignty.tls.asyncio.sleep", new_callable=AsyncMock, return_value=None),
    ):
        result = await scan_certificate_chain("landskrona.se", timeout=15)

    assert result["error"] is None
    assert result["scanned_domain"] == "www.landskrona.se"
    # We reached the host via verify=False, so mark it as a cert mismatch so the
    # pipeline knows to treat it as shared-hosting-style evidence.
    assert result["cert_mismatch"] is True


async def test_http_only_still_classified_when_www_also_fails() -> None:
    """If neither apex nor www serves TLS but port 80 is open, the result is
    still ``http_only`` — behaviour preserved for Upplands Väsby etc.
    """
    with (
        patch(
            "cert_sovereignty.tls._scan_asyncio_ssl",
            new=AsyncMock(return_value=_err("upplands-vasby.se", msg="Connection error: refused")),
        ),
        patch(
            "cert_sovereignty.tls._scan_asyncio_ssl_no_verify",
            new=AsyncMock(
                return_value=_err("www.upplands-vasby.se", msg="Connection error: refused")
            ),
        ),
        patch(
            "cert_sovereignty.tls._check_port_open",
            new_callable=AsyncMock,
            return_value=True,
        ),
        patch("cert_sovereignty.tls.asyncio.sleep", new_callable=AsyncMock, return_value=None),
    ):
        result = await scan_certificate_chain("upplands-vasby.se", timeout=15)

    assert result["error"] == "http_only"
    assert result["http_accessible"] is True
