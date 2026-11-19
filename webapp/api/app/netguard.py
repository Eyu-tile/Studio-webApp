"""Library links are fetched by our servers, so a link must not be able to reach anything private: the worker's own
files, the cloud metadata service (169.254.169.254), the cluster network, localhost. Checked when a link is added
and again right before every scan (DNS can change in between)."""
import ipaddress
import socket
from urllib.parse import urlsplit

from .config import get_settings


class UnsafeURL(ValueError):
    pass


def check_public_url(url: str) -> str:
    u = urlsplit(url.strip())
    if u.scheme not in ("http", "https"):
        raise UnsafeURL("only http(s) links")
    if u.username or u.password:
        raise UnsafeURL("links with a username or password inside aren't accepted")
    host = u.hostname
    if not host:
        raise UnsafeURL("the link has no host")
    if get_settings().library_allow_private_hosts:
        return url.strip()
    try:
        infos = socket.getaddrinfo(host, u.port or (443 if u.scheme == "https" else 80), type=socket.SOCK_STREAM)
    except socket.gaierror:
        raise UnsafeURL(f"{host} can't be found")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global or ip.is_multicast:
            raise UnsafeURL(f"{host} points to a private or internal address")
    return url.strip()


def detect_provider(url: str) -> str:
    host = (urlsplit(url).hostname or "").lower()
    if host.endswith(("drive.google.com", "docs.google.com")):
        return "gdrive"
    if host.endswith(("frame.io", "f.io")):
        return "frameio"
    if host.endswith("dropbox.com"):
        return "dropbox"
    if host.endswith(("1drv.ms", "onedrive.live.com", "sharepoint.com")):
        return "onedrive"
    path = urlsplit(url).path.lower()
    if path.rsplit(".", 1)[-1] in {"mp4", "mov", "m4v", "mkv", "webm", "jpg", "jpeg", "png", "webp", "mp3", "wav", "m4a"}:
        return "direct"
    return "web"
