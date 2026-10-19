"""Cliente HTTP com headers realistas, User-Agent rotativo, retries e detecção de bloqueio."""
from __future__ import annotations

import logging
import random
import time
from typing import Any, Dict, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from . import config

log = logging.getLogger(__name__)


class FetchError(Exception):
    """Falha ao obter uma página (rede, HTTP != 2xx...)."""


class BlockedError(FetchError):
    """O site bloqueou a requisição (403/429/CAPTCHA)."""


BLOCK_MARKERS = (
    "captcha",
    "robot check",
    "api-services-support@amazon.com",
    "digite os caracteres",
    "unusual traffic",
    "access denied",
    "are you a human",
    "px-captcha",
)


def looks_blocked(text: str) -> bool:
    """Páginas de CAPTCHA/bloqueio são pequenas; páginas reais de busca são grandes."""
    if not text or len(text) > 40_000:
        return False
    low = text.lower()
    return any(marker in low for marker in BLOCK_MARKERS)


class HttpClient:
    def __init__(
        self,
        timeout: int = config.REQUEST_TIMEOUT,
        min_delay: float = config.MIN_DELAY,
        max_delay: float = config.MAX_DELAY,
        max_retries: int = config.MAX_RETRIES,
    ) -> None:
        self.timeout = timeout
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.session = requests.Session()
        retry = Retry(
            total=max_retries,
            connect=max_retries,
            read=max_retries,
            backoff_factor=1.2,
            status_forcelist=(500, 502, 503, 504),  # 403/429 tratados manualmente (troca de UA)
            allowed_methods=frozenset(["GET", "POST"]),
            respect_retry_after_header=True,
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        self._user_agent = random.choice(config.USER_AGENTS)
        self._last_request = 0.0

    # -------------------------------------------------------------- helpers
    def rotate_user_agent(self) -> None:
        others = [ua for ua in config.USER_AGENTS if ua != self._user_agent]
        self._user_agent = random.choice(others or config.USER_AGENTS)
        self.session.cookies.clear()

    def _headers(self, referer: Optional[str], expect_json: bool, extra: Optional[Dict[str, str]]) -> Dict[str, str]:
        headers = {
            "User-Agent": self._user_agent,
            "Accept": (
                "application/json, text/plain, */*"
                if expect_json
                else "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
            ),
            "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
            "DNT": "1",
        }
        if not expect_json:
            headers.update(
                {
                    "Upgrade-Insecure-Requests": "1",
                    "Sec-Fetch-Dest": "document",
                    "Sec-Fetch-Mode": "navigate",
                    "Sec-Fetch-Site": "same-origin" if referer else "none",
                    "Sec-Fetch-User": "?1",
                }
            )
        if referer:
            headers["Referer"] = referer
        if extra:
            headers.update(extra)
        return headers

    def _wait(self) -> None:
        elapsed = time.time() - self._last_request
        pause = random.uniform(self.min_delay, self.max_delay)
        if self._last_request and elapsed < pause:
            time.sleep(pause - elapsed)

    # -------------------------------------------------------------- requests
    def request(
        self,
        method: str,
        url: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        referer: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
        expect_json: bool = False,
    ) -> requests.Response:
        for attempt in range(2):  # 2ª tentativa com outro User-Agent se houver bloqueio
            self._wait()
            try:
                response = self.session.request(
                    method,
                    url,
                    params=params,
                    data=data,
                    headers=self._headers(referer, expect_json, headers),
                    timeout=self.timeout,
                    allow_redirects=True,
                )
            except requests.RequestException as exc:
                raise FetchError(f"Falha de rede em {url}: {exc}") from exc
            finally:
                self._last_request = time.time()

            blocked = response.status_code in (403, 429) or (
                response.ok and not expect_json and looks_blocked(response.text)
            )
            if blocked:
                log.warning("Possível bloqueio em %s (HTTP %s)", url, response.status_code)
                if attempt == 0:
                    self.rotate_user_agent()
                    time.sleep(random.uniform(2.0, 4.0))
                    continue
                raise BlockedError(f"Bloqueado ao acessar {url} (HTTP {response.status_code})")
            if not response.ok:
                raise FetchError(f"HTTP {response.status_code} em {url}")
            return response
        raise FetchError(f"Falha inesperada ao acessar {url}")  # pragma: no cover

    def get(self, url: str, **kwargs: Any) -> requests.Response:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> requests.Response:
        return self.request("POST", url, **kwargs)
