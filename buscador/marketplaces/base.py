"""Interface comum dos marketplaces."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, List, Optional, Tuple

from bs4 import BeautifulSoup

from ..browser import Browser
from ..http_client import HttpClient
from ..models import Offer


class Marketplace(ABC):
    key: str = ""
    name: str = ""
    requires_browser: bool = False  # True -> precisa do Playwright

    def __init__(self, http: HttpClient, browser: Optional[Browser] = None, limit: int = 40) -> None:
        self.http = http
        self.browser = browser
        self.limit = limit

    def soup(self, url: str, **kwargs: Any) -> Tuple[BeautifulSoup, Any]:
        response = self.http.get(url, **kwargs)
        return BeautifulSoup(response.text, "html.parser"), response

    @abstractmethod
    def search(self, query: str) -> List[Offer]:
        """Busca o produto e devolve ofertas com URL DIRETA do anúncio."""

    def enrich(self, offer: Offer) -> Offer:
        """Abre a página da oferta para completar vendedor/reputação/vendas. Altera e devolve `offer`."""
        return offer
