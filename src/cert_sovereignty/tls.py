"""TLS certificate chain scanner.

Primary: asyncio SSL with explicit IPv4 resolution via the robust multi-resolver
in ``dns.py`` (system → Quad9 → Cloudflare → Google). This avoids a class of
false "unknown" classifications where the scanner runner's system resolver
hiccups for a second and marks a whole batch of municipalities as
``Connection error: [Errno -3] Temporary failure in name resolution``.

Root cause of most timeouts: Nordic municipal servers have both A and AAAA records,
but their IPv6 port 443 endpoints are firewalled/unreachable. asyncio.open_connection
on macOS prefers IPv6 (like most modern stacks), causing 15-second timeouts for servers
that work fine on IPv4 in under 300ms.

Fix: resolve IPv4 address explicitly and connect to it (passing server_hostname for SNI).

Recovery chain when primary fails:
  1. www fallback            — try www.{domain}:443
  2. Cert mismatch recovery  — SSL verify failed → connect without verify (shared hosting)
  3. Norwegian .no fallback  — bare .no domain fails → retry {slug}.kommune.no
  4. HTTP-only safety-net    — before marking http_only, try www.{domain} with
                               verification disabled (catches slow/IPv6-broken
                               hosts that do serve TLS).
  5. HTTP-only probe         — timeout/reset → check if port 80 is open
  6. Transient-error retry   — if the final state is a DNS/timeout/reset style
                               error, wait briefly and retry the whole chain
                               once with a longer timeout (captures slow
                               self-hosted servers like avesta.se).

Additional enrichment after successful scan:
  7. HTTPS redirect following — if domain redirects to a different host (e.g.
     stockholm.se → start.stockholm), scan the redirect target instead so we
     classify the CA actually serving municipality content.
"""

from __future__ import annotations

import asyncio
import ssl
from datetime import UTC, datetime

import httpx
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from loguru import logger

from .dns import lookup_a
from .models import CertChainEntry, Evidence, SignalKind
from .signatures import SIGNATURES, match_patterns

WEIGHTS: dict[SignalKind, float] = {
    SignalKind.LEAF_ISSUER: 0.35,
    SignalKind.INTERMEDIATE_ISSUER: 0.25,
    SignalKind.ROOT_CA: 0.15,
    SignalKind.CAA_RECORD: 0.10,
    SignalKind.CT_LOG: 0.08,
    SignalKind.OCSP_ENDPOINT: 0.04,
    SignalKind.CRL_ENDPOINT: 0.03,
}

# Retryable transient-looking error prefixes. These are the situations where a
# second attempt (possibly with a longer timeout) has a meaningful chance of
# succeeding — DNS glitches on the runner, slow self-hosted servers, etc.
_RETRY_ERRORS = (
    "Connection timeout",
    "Connection error",
    "Connection reset",
    "DNS resolution failed",
)

# Upper bound for the widened retry timeout. The first pass uses the caller's
# ``timeout`` argument (default 15 s); the retry uses ``min(timeout * 3, _MAX_RETRY_TIMEOUT)``.
_MAX_RETRY_TIMEOUT = 45

# Short backoff between the first pass and the retry. Long enough to let a
# transient DNS glitch settle, short enough that it does not dominate scan time.
_RETRY_BACKOFF_SECONDS = 2.0


def _no_kommune_fallback(domain: str) -> str | None:
    """Derive the {slug}.kommune.no fallback for a Norwegian bare .no domain.

    Examples::
        'www.nord-fron.no' → 'nord-fron.kommune.no'
        'amot.no'          → 'amot.kommune.no'
        'amot.kommune.no'  → None  (already authoritative)
        'vinje.herad.no'   → None  (already authoritative)
        'stavanger.no'     → 'stavanger.kommune.no'

    Returns None when the domain is already authoritative or not Norwegian.
    """
    bare = domain.removeprefix("www.")
    if not bare.endswith(".no"):
        return None
    if bare.endswith(".kommune.no") or bare.endswith(".herad.no"):
        return None
    slug = bare.removesuffix(".no")
    if not slug:
        return None
    return f"{slug}.kommune.no"


async def scan_certificate_chain(domain: str, port: int = 443, timeout: int = 15) -> dict:
    """Scan TLS cert chain with full recovery chain + redirect following.

    Runs the recovery chain once at the caller-supplied ``timeout``. If the
    final state is a transient-looking error (timeout, connection reset, DNS
    glitch on the scanner runner) we wait ``_RETRY_BACKOFF_SECONDS`` and retry
    the whole chain once with a widened timeout. This second pass is the one
    that captures e.g. self-hosted Swedish municipalities like ``avesta.se``
    whose apex serves TLS but needs >15 s to finish the handshake, and whole
    batches of SiteVision-hosted sites hit by a single runner-side DNS hiccup.
    """
    result = await _scan_with_recovery_chain(domain, port, timeout)

    # ── Recovery 6: transient-error retry ─────────────────────────────────────
    if _is_transient_error(result.get("error")):
        retry_timeout = min(timeout * 3, _MAX_RETRY_TIMEOUT)
        logger.debug(
            "Retrying {} after transient error ({}) with timeout {}s",
            domain,
            result.get("error"),
            retry_timeout,
        )
        await asyncio.sleep(_RETRY_BACKOFF_SECONDS)
        retry = await _scan_with_recovery_chain(domain, port, retry_timeout)
        if not retry.get("error") or not _is_transient_error(retry.get("error")):
            return retry

    return result


def _is_transient_error(error: str | None) -> bool:
    """Return True when ``error`` looks transient enough to warrant a retry."""
    if not error:
        return False
    # ``http_only`` is a *terminal* classification (we proved port 80 is open
    # and 443 isn't) — never retry those, they are genuinely not HTTPS.
    if error == "http_only":
        return False
    return any(marker in error for marker in _RETRY_ERRORS)


async def _scan_with_recovery_chain(domain: str, port: int, timeout: int) -> dict:
    """One full pass of the recovery chain (without the outer transient retry)."""
    result = await _scan_asyncio_ssl(domain, port, timeout)

    # ── Recovery 1: www fallback ──────────────────────────────────────────────
    if result["error"] and not domain.startswith("www."):
        www = await _scan_asyncio_ssl(f"www.{domain}", port, timeout)
        if not www["error"]:
            www["domain"] = domain
            www["scanned_domain"] = f"www.{domain}"
            return www

    # ── Recovery 2: cert mismatch → shared hosting ─────────────────────────────────
    if result["error"] and "SSL verification failed" in result["error"]:
        shared = await _scan_asyncio_ssl_no_verify(domain, port, min(timeout, 10))
        if not shared.get("error") and shared.get("chain"):
            shared["domain"] = domain
            shared["cert_mismatch"] = True
            return shared
        if not domain.startswith("www."):
            shared_www = await _scan_asyncio_ssl_no_verify(f"www.{domain}", port, min(timeout, 10))
            if not shared_www.get("error") and shared_www.get("chain"):
                shared_www["domain"] = domain
                shared_www["scanned_domain"] = f"www.{domain}"
                shared_www["cert_mismatch"] = True
                return shared_www

    # ── Recovery 3: Norwegian bare .no → {slug}.kommune.no fallback ───────────────
    # Bare .no domains (e.g. www.amot.no) may have TLS SNI mismatches, timeouts,
    # or CNAME to commercial sites. The authoritative Norwegian municipal domain
    # is always {slug}.kommune.no (or .herad.no — already excluded by helper).
    # This recovery fires for ANY error type: ssl_error, timeout, connection_error.
    if result["error"]:
        kommune_domain = _no_kommune_fallback(domain)
        if kommune_domain:
            logger.debug("Norwegian .no fallback: {} → {}", domain, kommune_domain)
            kommune = await _scan_asyncio_ssl(kommune_domain, port, timeout)
            if not kommune["error"]:
                kommune["domain"] = domain
                kommune["scanned_domain"] = kommune_domain
                return kommune

    # ── Recovery 4: HTTP-only safety-net ───────────────────────────────────────
    # Before we commit to ``http_only`` (which is sticky and ends up in the UI
    # as "Unknown"), give the ``www`` host one more chance with verification
    # disabled. A few Swedish municipalities (e.g. landskrona.se, skara.se) were
    # previously misclassified as http_only because their apex either times out
    # or serves a cert whose SAN does not cover it — the real TLS endpoint lives
    # on ``www.<domain>`` with a perfectly valid cert.
    if result["error"] and any(s in result["error"] for s in _RETRY_ERRORS):
        if not domain.startswith("www."):
            www_noverify = await _scan_asyncio_ssl_no_verify(
                f"www.{domain}", port, min(timeout, 10)
            )
            if not www_noverify.get("error") and www_noverify.get("chain"):
                www_noverify["domain"] = domain
                www_noverify["scanned_domain"] = f"www.{domain}"
                www_noverify["cert_mismatch"] = True
                return www_noverify

    # ── Recovery 5: HTTP-only probe ────────────────────────────────────────────
    if result["error"] and any(s in result["error"] for s in _RETRY_ERRORS):
        http_ok = await _check_port_open(domain, 80, timeout=5)
        result["http_accessible"] = http_ok
        if http_ok:
            result["error"] = "http_only"

    # ── Enrichment 7: HTTPS cross-domain redirect following ─────────────────────────
    # Only run when we successfully got a cert — check if the domain redirects
    # to a different host (e.g. stockholm.se → start.stockholm). If so, the
    # redirect target is the actual municipal website; scan it instead.
    if not result["error"] and result.get("chain"):
        redirect_host = await _follow_https_redirect(domain, timeout=6)
        if redirect_host:
            logger.debug("Following cross-domain redirect: {} → {}", domain, redirect_host)
            redir_result = await _scan_asyncio_ssl(redirect_host, port, min(timeout, 10))
            if not redir_result.get("error") and redir_result.get("chain"):
                redir_result["domain"] = domain
                redir_result["scanned_domain"] = redirect_host
                return redir_result

    return result


async def _scan_asyncio_ssl(domain: str, port: int, timeout: int) -> dict:
    return await _connect_and_scan(domain, port, timeout, verify=True)


async def _scan_asyncio_ssl_no_verify(domain: str, port: int, timeout: int) -> dict:
    return await _connect_and_scan(domain, port, timeout, verify=False)


async def _connect_and_scan(domain: str, port: int, timeout: int, verify: bool) -> dict:
    """Core TLS scan. Prefers IPv4 to avoid broken-IPv6 timeouts."""
    result: dict = {
        "domain": domain,
        "scan_timestamp": datetime.now(UTC).isoformat(),
        "chain": [],
        "evidence": [],
        "tls_version": "",
        "verification": "",
        "error": None,
        "cert_mismatch": False,
        "http_accessible": None,
    }

    try:
        ssl_ctx = ssl.create_default_context()
        if not verify:
            ssl_ctx.check_hostname = False
            ssl_ctx.verify_mode = ssl.CERT_NONE

        # Resolve to IPv4 explicitly to avoid broken-IPv6 endpoints AND to avoid
        # transient system-resolver failures (``[Errno -3] Temporary failure in
        # name resolution``) marking whole batches of municipalities as
        # ``connection_error``. ``lookup_a`` uses a multi-resolver fallback
        # chain (system → Quad9 → Cloudflare → Google) and returns [] only
        # when every resolver has failed — which we treat as an authoritative
        # ``DNS resolution failed`` (still retryable by the outer retry).
        try:
            ipv4_addrs = await lookup_a(domain)
        except Exception as e:
            logger.debug("Robust DNS lookup raised for {}: {}", domain, e)
            ipv4_addrs = []
        if not ipv4_addrs:
            result["error"] = f"DNS resolution failed: no A record for {domain}"
            return result
        connect_target = ipv4_addrs[0]

        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(connect_target, port, ssl=ssl_ctx, server_hostname=domain),
            timeout=timeout,
        )

        ssl_obj = writer.get_extra_info("ssl_object")
        if ssl_obj:
            result["tls_version"] = ssl_obj.version() or ""
            result["verification"] = "OK" if verify else "unverified"
            der_cert = ssl_obj.getpeercert(binary_form=True)
            if der_cert:
                cert = x509.load_der_x509_certificate(der_cert, default_backend())
                entry = _parse_x509_cert(cert, 0, "leaf")
                result["chain"].append(entry)
                result["evidence"].extend(_match_cert_to_ca(entry, SignalKind.LEAF_ISSUER))
            if hasattr(ssl_obj, "get_verified_chain"):
                try:
                    for i, der in enumerate(ssl_obj.get_verified_chain()[1:], start=1):
                        cert = x509.load_der_x509_certificate(der, default_backend())
                        ct = "root" if cert.subject == cert.issuer else "intermediate"
                        entry = _parse_x509_cert(cert, i, ct)
                        result["chain"].append(entry)
                        kind = (
                            SignalKind.ROOT_CA if ct == "root" else SignalKind.INTERMEDIATE_ISSUER
                        )
                        result["evidence"].extend(_match_cert_to_ca(entry, kind))
                except Exception:
                    pass

        writer.close()
        try:
            await asyncio.wait_for(writer.wait_closed(), timeout=2)
        except Exception:
            pass

    except TimeoutError:
        result["error"] = f"Connection timeout ({timeout}s)"
    except ssl.SSLCertVerificationError as e:
        result["error"] = f"SSL verification failed: {e}"
    except ssl.SSLError as e:
        result["error"] = f"SSL error: {e}"
    except (ConnectionRefusedError, ConnectionResetError, OSError) as e:
        result["error"] = f"Connection error: {e}"
    except Exception as e:
        result["error"] = f"{type(e).__name__}: {e}"
        logger.debug("TLS scan error for {}: {}", domain, e)

    return result


# ── HTTPS redirect following ──────────────────────────────────────────────────


async def _follow_https_redirect(domain: str, timeout: int = 6) -> str | None:
    """Return the final hostname after following HTTPS redirects, or None.

    Returns None if:
    - No redirect occurs (final host == original domain)
    - The redirect is only path/query (same host, e.g. /en → /)
    - Request fails

    Uses httpx (already a project dependency) with verify=False so we can
    detect redirects even from servers with cert mismatches.
    """
    try:
        async with httpx.AsyncClient(
            verify=False,
            follow_redirects=True,
            timeout=timeout,
        ) as client:
            resp = await client.head(f"https://{domain}/")
            # Use removeprefix, not lstrip — lstrip strips any char in the string
            final_host = resp.url.host.lower().removeprefix("www.")
            original = domain.lower().removeprefix("www.")
            if final_host != original:
                # Cross-domain redirect found
                return resp.url.host  # Return actual final host including www if present
    except Exception:
        pass
    return None


# ── HTTP-only probe ───────────────────────────────────────────────────────────


async def _check_port_open(domain: str, port: int, timeout: int = 5) -> bool:
    """Return True if a TCP connection to domain:port succeeds within timeout.

    Uses the same robust multi-resolver as ``_connect_and_scan`` so a system
    resolver hiccup does not cause us to wrongly classify a reachable host as
    unreachable.
    """
    try:
        try:
            ipv4_addrs = await lookup_a(domain)
        except Exception:
            ipv4_addrs = []
        if not ipv4_addrs:
            return False
        target = ipv4_addrs[0]

        _, writer = await asyncio.wait_for(
            asyncio.open_connection(target, port),
            timeout=timeout,
        )
        writer.close()
        try:
            await asyncio.wait_for(writer.wait_closed(), timeout=1)
        except Exception:
            pass
        return True
    except Exception:
        return False


# ── Certificate parsing ───────────────────────────────────────────────────────


def _get_name_attr(name: x509.Name, oid: object) -> str:
    try:
        attrs = name.get_attributes_for_oid(oid)  # type: ignore[arg-type]
        # attrs[0].value is str | bytes in cryptography's stubs; we always
        # receive str for standard DN attributes (CN, O, C) — cast explicitly
        value = attrs[0].value if attrs else ""
        return value if isinstance(value, str) else value.decode("utf-8", errors="replace")
    except Exception:
        return ""


def _parse_x509_cert(cert: x509.Certificate, position: int, cert_type: str) -> CertChainEntry:
    OID = x509.oid.NameOID
    return CertChainEntry(
        position=position,
        cert_type=cert_type,
        subject_cn=_get_name_attr(cert.subject, OID.COMMON_NAME),
        subject_org=_get_name_attr(cert.subject, OID.ORGANIZATION_NAME),
        subject_country=_get_name_attr(cert.subject, OID.COUNTRY_NAME),
        issuer_cn=_get_name_attr(cert.issuer, OID.COMMON_NAME),
        issuer_org=_get_name_attr(cert.issuer, OID.ORGANIZATION_NAME),
        issuer_country=_get_name_attr(cert.issuer, OID.COUNTRY_NAME),
        not_before=cert.not_valid_before_utc.isoformat(),
        not_after=cert.not_valid_after_utc.isoformat(),
        serial_hex=hex(cert.serial_number),
        sig_algorithm=cert.signature_algorithm_oid.dotted_string,
        sha256_fingerprint=cert.fingerprint(hashes.SHA256()).hex().upper(),
    )


def _match_cert_to_ca(entry: CertChainEntry, kind: SignalKind) -> list[Evidence]:
    results: list[Evidence] = []
    for sig in SIGNATURES:
        matched = False
        detail_parts: list[str] = []
        if match_patterns(entry.issuer_org, sig.issuer_org_patterns):
            matched = True
            detail_parts.append(f"issuer_org={entry.issuer_org}")
        if match_patterns(entry.issuer_cn, sig.issuer_cn_patterns):
            matched = True
            detail_parts.append(f"issuer_cn={entry.issuer_cn}")
        if kind == SignalKind.ROOT_CA and match_patterns(entry.subject_cn, sig.root_cn_patterns):
            matched = True
            detail_parts.append(f"root_cn={entry.subject_cn}")
        if matched:
            results.append(
                Evidence(
                    kind=kind,
                    jurisdiction=sig.jurisdiction,
                    ca_name=sig.name,
                    weight=WEIGHTS[kind],
                    detail=f"{kind.value}: {', '.join(detail_parts)} → {sig.name}",
                    raw=f"{entry.issuer_org}|{entry.issuer_cn}",
                )
            )
    return results


def _extract_pem_certs(showcerts_output: str) -> list[str]:
    pems: list[str] = []
    current: list[str] = []
    in_cert = False
    for line in showcerts_output.split("\n"):
        if "-----BEGIN CERTIFICATE-----" in line:
            in_cert = True
            current = [line]
        elif "-----END CERTIFICATE-----" in line:
            current.append(line)
            pems.append("\n".join(current))
            in_cert = False
        elif in_cert:
            current.append(line)
    return pems
