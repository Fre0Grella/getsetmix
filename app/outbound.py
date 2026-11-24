"""Requests GetSetMix makes to other servers (cover images, cover search).

One User-Agent and one timeout for all of them. Some image hosts refuse a
client that does not look like a browser, hence the "Mozilla/5.0" prefix.
"""
from __future__ import annotations

import urllib.request
from http.client import HTTPResponse

USER_AGENT = "Mozilla/5.0 (GetSetMix/1.0)"
TIMEOUT = 20  # seconds


def open_url(url: str, timeout: float = TIMEOUT) -> HTTPResponse:
    """GET `url` with the app's User-Agent; the caller closes the response."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    return urllib.request.urlopen(req, timeout=timeout)
