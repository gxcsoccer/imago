from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse


def _is_private_ip(hostname: str) -> bool:
    """Return True if *hostname* is or resolves to a non-globally-routable IP.

    Literal IP addresses are checked directly.  Hostnames are resolved via
    :func:`socket.getaddrinfo`; if DNS is unavailable the check fails-open
    (returns False) so that offline / sandboxed environments still work.
    """
    # Check literal IP addresses immediately.
    try:
        addr = ipaddress.ip_address(hostname)
        # Unwrap IPv4-mapped IPv6 (e.g. ::ffff:192.168.1.1).
        if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped is not None:
            return not addr.ipv4_mapped.is_global
        return not addr.is_global
    except ValueError:
        pass  # hostname, not a literal IP

    # Resolve the hostname and check every returned address.
    try:
        infos = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
        for _family, _type, _proto, _canonname, sockaddr in infos:
            ip_str = sockaddr[0]
            try:
                addr = ipaddress.ip_address(ip_str)
                if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped is not None:
                    if not addr.ipv4_mapped.is_global:
                        return True
                elif not addr.is_global:
                    return True
            except ValueError:
                continue
        return False
    except socket.gaierror:
        return False  # DNS unavailable → fail-open


def assert_safe_url(url: str) -> None:
    """Raise :exc:`ValueError` if *url* is not safe for outbound requests.

    Checks performed:

    * Scheme must be ``http`` or ``https``.
    * Hostname must be present.
    * Hostname must not resolve to a private / reserved IP address (SSRF guard).
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(
            f"URL scheme must be 'http' or 'https', got {parsed.scheme!r}"
        )
    hostname = parsed.hostname
    if not hostname:
        raise ValueError("URL has no hostname")
    if _is_private_ip(hostname):
        raise ValueError(
            "URL hostname resolves to a private or reserved IP address"
        )
