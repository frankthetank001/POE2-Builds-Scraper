"""A small throttled, retrying HTTP client shared by the snapshot/roster/character calls."""

from __future__ import annotations

import logging
import time

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from .config import Settings

logger = logging.getLogger(__name__)


class PoeNinjaClient:
    """Browser-like GET client. poe.ninja gates on a normal UA + Referer (no auth)."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._last_request = 0.0
        self._client = httpx.Client(
            timeout=settings.timeout_s,
            headers={
                "User-Agent": settings.user_agent,
                "Accept": "*/*",
                "Referer": f"https://poe.ninja/poe2/builds/{settings.league_slug}",
            },
            follow_redirects=True,
        )

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request
        wait = self.settings.request_delay_s - elapsed
        if wait > 0:
            time.sleep(wait)
        self._last_request = time.monotonic()

    def get(self, url: str, *, params: dict | None = None) -> httpx.Response:
        @retry(
            retry=retry_if_exception_type((httpx.TransportError, httpx.HTTPStatusError)),
            wait=wait_exponential(multiplier=1, min=1, max=30),
            stop=stop_after_attempt(self.settings.max_retries),
            reraise=True,
        )
        def _do() -> httpx.Response:
            self._throttle()
            resp = self._client.get(url, params=params)
            # Honor explicit backoff if poe.ninja ever sends one.
            if resp.status_code == 429:
                retry_after = float(resp.headers.get("Retry-After", "5"))
                logger.warning("429 from poe.ninja; sleeping %.1fs", retry_after)
                time.sleep(retry_after)
                resp.raise_for_status()
            if resp.status_code >= 500:
                resp.raise_for_status()
            return resp

        return _do()

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "PoeNinjaClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
