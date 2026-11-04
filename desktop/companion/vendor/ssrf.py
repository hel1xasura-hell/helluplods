"""SSRF protection for every outbound fetch/browse of owner- or web-supplied URLs."""
import ipaddress
import socket
from urllib.parse import urlsplit

ALLOWED_SCHEMES = {"http", "https"}
BLOCKED_HOSTS = {"localhost", "metadata.google.internal"}


class UnsafeURL(ValueError):
    pass


def _check_ip(ip: str) -> None:
    addr = ipaddress.ip_address(ip)
    if (
        addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_multicast
        or addr.is_reserved or addr.is_unspecified
        or (addr.version == 6 and addr.ipv4_mapped and not addr.ipv4_mapped.is_global)
    ):
        raise UnsafeURL(f"Address {ip} is not publicly routable")


def validate_public_url(url: str, resolve: bool = True) -> str:
    parts = urlsplit(url.strip())
    if parts.scheme not in ALLOWED_SCHEMES:
        raise UnsafeURL("Only http and https URLs are allowed")
    if parts.username or parts.password:
        raise UnsafeURL("URLs with embedded credentials are not allowed")
    host = (parts.hostname or "").lower()
    if not host or host in BLOCKED_HOSTS or host.endswith(".internal") or host.endswith(".local"):
        raise UnsafeURL("Host is not allowed")
    try:
        _check_ip(host)  # literal IP
        return url
    except ValueError as exc:
        if isinstance(exc, UnsafeURL):
            raise
    if resolve:
        try:
            infos = socket.getaddrinfo(host, parts.port or (443 if parts.scheme == "https" else 80))
        except socket.gaierror as exc:
            raise UnsafeURL("Host could not be resolved") from exc
        for info in infos:
            _check_ip(info[4][0])
    return url
