"""Shopee Brasil (experimental): captura o JSON interno da busca via Playwright.

A Shopee tem proteção anti-bot agressiva; é comum cair em login/CAPTCHA. Se isso ocorrer,
o status aparece no relatório. Alternativa estável: Shopee Affiliate Open API.
O link usa o formato curto https://shopee.com.br/product/<shopid>/<itemid>.
"""
from __future__ import annotations

from typing import Any, Iterable, List, Optional
from urllib.parse import quote

from ..models import Offer
from ..utils import clean_text
from .base import Marketplace

BASE = "https://shopee.com.br"


class Shopee(Marketplace):
    key = "shopee"
    name = "Shopee"
    requires_browser = True

    def search(self, query: str) -> List[Offer]:
        payloads = self.browser.capture_json(
            f"{BASE}/search?keyword={quote(query)}", "api/v4/search/search_items"
        )
        offers: List[Offer] = []
        seen = set()
        for payload in payloads:
            for entry in self._items(payload):
                offer = self._to_offer(entry)
                if offer and offer.url not in seen:
                    seen.add(offer.url)
                    offers.append(offer)
        return offers[: self.limit]

    @staticmethod
    def _items(payload: Any) -> Iterable[dict]:
        if not isinstance(payload, dict):
            return []
        items = payload.get("items") or (payload.get("data") or {}).get("items") or []
        return [i for i in items if isinstance(i, dict)]

    @staticmethod
    def _to_offer(entry: dict) -> Optional[Offer]:
        item = entry.get("item_basic") or entry
        shop_id, item_id = item.get("shopid"), item.get("itemid")
        raw_price = item.get("price") or item.get("price_min")
        name = clean_text(item.get("name"))
        if not (shop_id and item_id and raw_price and name):
            return None
        rating = item.get("item_rating") or {}
        counts = rating.get("rating_count") or []
        official = bool(item.get("is_official_shop"))
        verified = bool(item.get("shopee_verified"))
        return Offer(
            marketplace="Shopee",
            title=name,
            price=raw_price / 100_000,  # a Shopee devolve preço em micro-unidades
            url=f"{BASE}/product/{shop_id}/{item_id}",
            shipping=0.0 if item.get("show_free_shipping") else None,
            seller=item.get("shop_name"),
            seller_badge="Loja Oficial" if official else ("Shopee Verificado" if verified else None),
            official_store=official,
            sold_qty=item.get("historical_sold") or item.get("sold"),
            reviews_count=counts[0] if counts else None,
            product_rating=rating.get("rating_star") or None,
        )
