"""Tests for the SSRF-prevention utilities in imago.security."""
from __future__ import annotations

import socket
from unittest.mock import patch

import pytest

from imago.security import _is_private_ip, assert_safe_url


# ── _is_private_ip ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "addr",
    [
        "127.0.0.1",       # IPv4 loopback
        "127.255.255.255", # IPv4 loopback range edge
        "10.0.0.1",        # RFC 1918 Class A
        "172.16.0.1",      # RFC 1918 Class B
        "172.31.255.255",  # RFC 1918 Class B edge
        "192.168.1.1",     # RFC 1918 Class C
        "169.254.0.1",     # IPv4 link-local
        "0.0.0.0",         # Unspecified
        "240.0.0.1",       # Reserved
        "::1",             # IPv6 loopback
        "fe80::1",         # IPv6 link-local
    ],
)
def test_private_literal_ips_are_blocked(addr):
    assert _is_private_ip(addr) is True


@pytest.mark.parametrize(
    "addr",
    [
        "1.2.3.4",
        "8.8.8.8",
        "93.184.216.34",  # example.com
        "2606:2800:21f:cb07:6820:80da:af6b:8b2c",  # example.com IPv6
    ],
)
def test_public_literal_ips_are_allowed(addr):
    assert _is_private_ip(addr) is False


def test_hostname_resolving_to_private_is_blocked():
    with patch("socket.getaddrinfo") as mock_dns:
        mock_dns.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 0)),
        ]
        assert _is_private_ip("evil.internal") is True


def test_hostname_resolving_to_public_is_allowed():
    with patch("socket.getaddrinfo") as mock_dns:
        mock_dns.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("1.2.3.4", 0)),
        ]
        assert _is_private_ip("example.com") is False


def test_hostname_dns_failure_is_fail_open():
    """If DNS is unavailable the check must not block the request."""
    with patch("socket.getaddrinfo", side_effect=socket.gaierror("no address")):
        assert _is_private_ip("example.com") is False


def test_ipv4_mapped_ipv6_private_is_blocked():
    """IPv4-mapped IPv6 addresses wrapping private IPs must be blocked."""
    # ::ffff:192.168.1.1 is IPv4-mapped IPv6 for 192.168.1.1
    assert _is_private_ip("::ffff:192.168.1.1") is True


# ── assert_safe_url ───────────────────────────────────────────────────────────


def test_safe_http_url_passes():
    with patch("socket.getaddrinfo") as mock_dns:
        mock_dns.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("1.2.3.4", 0)),
        ]
        assert_safe_url("http://example.com/path")  # must not raise


def test_safe_https_url_passes():
    with patch("socket.getaddrinfo") as mock_dns:
        mock_dns.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("1.2.3.4", 0)),
        ]
        assert_safe_url("https://example.com/path")  # must not raise


def test_public_ip_url_passes():
    assert_safe_url("http://1.2.3.4/path")  # must not raise


def test_private_ip_url_raises():
    with pytest.raises(ValueError, match="private"):
        assert_safe_url("http://127.0.0.1/admin")


def test_rfc1918_url_raises():
    with pytest.raises(ValueError, match="private"):
        assert_safe_url("http://192.168.1.1/")


def test_file_scheme_raises():
    with pytest.raises(ValueError, match="scheme"):
        assert_safe_url("file:///etc/passwd")


def test_ftp_scheme_raises():
    with pytest.raises(ValueError, match="scheme"):
        assert_safe_url("ftp://example.com/file")


def test_no_hostname_raises():
    with pytest.raises(ValueError, match="hostname"):
        assert_safe_url("http:///path")
