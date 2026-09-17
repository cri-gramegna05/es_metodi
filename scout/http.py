"""Polite HTTP layer: robots.txt, per-host rate limit, retry/backoff, disk cache."""

from __future__ import annotations

import hashlib
import random
import time
import urllib.robotparser
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx

from .config import HttpConfig
from .log import get_logger

log = get_logger(__name__)


class RobotsDisallowed(RuntimeError):
    """The site's robots.txt forbids this URL for our user-agent."""


@dataclass
class Response:
    url: str
    status: int
    text: str
    from_cache: bool = False

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300


@dataclass
class Fetcher:
    cfg: HttpConfig
    cache_dir: Path
    _robots: dict[str, urllib.robotparser.RobotFileParser | None] = field(default_factory=dict)
    _last_request: dict[str, float] = field(default_factory=dict)
    _client: httpx.Client | None = None

    def __post_init__(self) -> None:
        self.cache_dir = Path(self.cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._client = httpx.Client(
            timeout=self.cfg.timeout_seconds,
            follow_redirects=True,
            headers={
                "User-Agent": self.cfg.user_agent,
                "Accept-Language": "it-IT,it;q=0.9,en;q=0.8",
            },
        )

    def close(self) -> None:
        if self._client:
            self._client.close()

    def __enter__(self) -> "Fetcher":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # --- robots -----------------------------------------------------------

    def _robots_for(self, url: str) -> urllib.robotparser.RobotFileParser | None:
        parsed = urlparse(url)
        root = f"{parsed.scheme}://{parsed.netloc}"
        if root in self._robots:
            return self._robots[root]
        rp = urllib.robotparser.RobotFileParser()
        try:
            resp = self._client.get(f"{root}/robots.txt")  # type: ignore[union-attr]
            if resp.status_code == 200:
                rp.parse(resp.text.splitlines())
            elif resp.status_code in (401, 403):
                rp.disallow_all = True       # explicitly gated: treat as off-limits
            else:
                rp.allow_all = True          # no robots.txt: crawling is allowed
        except httpx.HTTPError as exc:
            log.warning("robots_fetch_failed", root=root, error=str(exc))
            rp = None                        # unknown: fail closed below
        self._robots[root] = rp
        return rp

    def allowed(self, url: str) -> bool:
        if not self.cfg.respect_robots:
            return True
        rp = self._robots_for(url)
        if rp is None:
            return False
        return rp.can_fetch(self.cfg.user_agent, url)

    def crawl_delay(self, url: str) -> float:
        rp = self._robots_for(url) if self.cfg.respect_robots else None
        declared = 0.0
        if rp is not None:
            try:
                value = rp.crawl_delay(self.cfg.user_agent)
                declared = float(value) if value else 0.0
            except Exception:
                declared = 0.0
        return max(self.cfg.request_delay_seconds, declared)

    # --- cache ------------------------------------------------------------

    def _cache_path(self, url: str) -> Path:
        h = hashlib.sha256(url.encode()).hexdigest()
        return self.cache_dir / h[:2] / f"{h}.html"

    def _cached(self, url: str) -> str | None:
        path = self._cache_path(url)
        if not path.exists():
            return None
        age = datetime.now(timezone.utc) - datetime.fromtimestamp(
            path.stat().st_mtime, tz=timezone.utc
        )
        if age > timedelta(hours=self.cfg.cache_ttl_hours):
            return None
        return path.read_text(encoding="utf-8", errors="replace")

    def _store(self, url: str, text: str) -> None:
        path = self._cache_path(url)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    # --- fetch ------------------------------------------------------------

    def _throttle(self, url: str) -> None:
        host = urlparse(url).netloc
        delay = self.crawl_delay(url)
        last = self._last_request.get(host)
        if last is not None:
            wait = delay - (time.monotonic() - last)
            if wait > 0:
                time.sleep(wait)
        self._last_request[host] = time.monotonic()

    def get(self, url: str, use_cache: bool = True) -> Response:
        """Fetch a URL, honouring robots.txt, cache, rate limit and retries."""
        if use_cache:
            cached = self._cached(url)
            if cached is not None:
                log.debug("http_cache_hit", url=url)
                return Response(url=url, status=200, text=cached, from_cache=True)

        if not self.allowed(url):
            raise RobotsDisallowed(url)

        last_error: Exception | None = None
        for attempt in range(self.cfg.max_retries):
            self._throttle(url)
            try:
                resp = self._client.get(url)  # type: ignore[union-attr]
            except httpx.HTTPError as exc:
                last_error = exc
            else:
                if resp.status_code < 400:
                    self._store(url, resp.text)
                    log.debug("http_ok", url=url, status=resp.status_code)
                    return Response(url=url, status=resp.status_code, text=resp.text)
                if resp.status_code in (403, 404, 410):
                    log.warning("http_refused", url=url, status=resp.status_code)
                    return Response(url=url, status=resp.status_code, text=resp.text)
                last_error = httpx.HTTPStatusError(
                    f"status {resp.status_code}", request=resp.request, response=resp
                )
            sleep_for = self.cfg.backoff_base_seconds * (2**attempt) + random.uniform(0, 1)
            log.warning("http_retry", url=url, attempt=attempt + 1, sleep=round(sleep_for, 1))
            time.sleep(sleep_for)

        raise RuntimeError(f"GET {url} failed after {self.cfg.max_retries} attempts: {last_error}")
