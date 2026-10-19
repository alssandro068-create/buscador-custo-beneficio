"""Wrapper opcional do Playwright (Chromium) para sites que renderizam via JavaScript."""
from __future__ import annotations

import logging
import random
from typing import Any, List, Optional

from . import config

log = logging.getLogger(__name__)


class BrowserUnavailable(Exception):
    """Playwright/Chromium não está instalado ou não pôde iniciar."""


def playwright_available() -> bool:
    try:
        import playwright.sync_api  # noqa: F401
        return True
    except ImportError:
        return False


class Browser:
    def __init__(self, headless: bool = True, timeout_ms: int = 35_000) -> None:
        self.headless = headless
        self.timeout_ms = timeout_ms
        self._pw = None
        self._browser = None
        self._context = None

    def __enter__(self) -> "Browser":
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise BrowserUnavailable("Instale: pip install playwright && python -m playwright install chromium") from exc
        self._pw = sync_playwright().start()
        try:
            self._browser = self._pw.chromium.launch(
                headless=self.headless,
                args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
            )
        except Exception as exc:  # navegador não instalado, etc.
            self._pw.stop()
            raise BrowserUnavailable(f"Não foi possível iniciar o Chromium: {exc}") from exc
        self._context = self._browser.new_context(
            user_agent=random.choice(config.CHROME_USER_AGENTS),
            locale="pt-BR",
            timezone_id="America/Sao_Paulo",
            viewport={"width": 1366, "height": 850},
            extra_http_headers={"Accept-Language": "pt-BR,pt;q=0.9,en;q=0.7"},
        )
        self._context.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
        return self

    def __exit__(self, *exc_info: Any) -> None:
        for closer in (
            getattr(self._context, "close", None),
            getattr(self._browser, "close", None),
            getattr(self._pw, "stop", None),
        ):
            try:
                if closer:
                    closer()
            except Exception:  # noqa: BLE001
                pass

    def render(self, url: str, wait_selector: Optional[str] = None, scroll_steps: int = 4) -> str:
        """Abre a página, espera o seletor, rola para carregar itens 'lazy' e devolve o HTML final."""
        from playwright.sync_api import TimeoutError as PWTimeout

        page = self._context.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=self.timeout_ms)
            if wait_selector:
                try:
                    page.wait_for_selector(wait_selector, timeout=self.timeout_ms)
                except PWTimeout:
                    log.warning("Seletor %r não apareceu em %s (bloqueio/CAPTCHA?)", wait_selector, url)
            for _ in range(scroll_steps):
                page.mouse.wheel(0, 1200)
                page.wait_for_timeout(random.randint(500, 1000))
            return page.content()
        finally:
            page.close()

    def capture_json(self, url: str, url_contains: str, wait_seconds: int = 10) -> List[Any]:
        """Abre a página e captura as respostas JSON de chamadas internas cuja URL contém `url_contains`."""
        captured: List[Any] = []
        page = self._context.new_page()

        def on_response(response: Any) -> None:
            try:
                if url_contains in response.url and response.status == 200:
                    captured.append(response.json())
            except Exception:  # noqa: BLE001
                pass

        page.on("response", on_response)
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=self.timeout_ms)
            page.wait_for_timeout(wait_seconds * 1000)
            if not captured:
                page.mouse.wheel(0, 1500)
                page.wait_for_timeout(3000)
        finally:
            page.close()
        return captured
