"""Amazon Brasil. O link é montado a partir do ASIN: https://www.amazon.com.br/dp/<ASIN>.

Se a página do produto revelar um vendedor terceiro, acrescenta `?m=<seller_id>` para apontar
para a oferta daquele vendedor. A Amazon bloqueia bastante (CAPTCHA), especialmente em IPs de
datacenter como os do GitHub Actions; rodar localmente tende a funcionar melhor.
"""
from __future__ import annotations

import re
from typing import List, Optional

from ..models import Offer
from ..utils import clean_text, parse_brl, parse_count, parse_days, parse_rating
from .base import Marketplace

BASE = "https://www.amazon.com.br"


class Amazon(Marketplace):
    key = "amazon"
    name = "Amazon"

    def search(self, query: str) -> List[Offer]:
        soup, _ = self.soup(f"{BASE}/s", params={"k": query}, referer=BASE + "/")
        offers: List[Offer] = []
        for card in soup.select('div[data-component-type="s-search-result"][data-asin]'):
            asin = (card.get("data-asin") or "").strip()
            if not re.fullmatch(r"[A-Z0-9]{10}", asin):
                continue
            title_node = card.select_one("h2")
            price_node = card.select_one("span.a-price:not(.a-text-price) span.a-offscreen")
            price = parse_brl(price_node.get_text()) if price_node else None
            title = clean_text(title_node.get_text(" ")) if title_node else ""
            if not title or price is None:
                continue

            text = clean_text(card.get_text(" "))
            low = text.lower()
            rating, reviews = None, None
            for node in card.select("[aria-label]"):
                label = node["aria-label"].lower()
                if "estrela" in label and rating is None:
                    rating = parse_rating(label)
            review_node = card.select_one("span.s-underline-text, a[href*='customerReviews'] span")
            if review_node:
                reviews = parse_count(review_node.get_text())
            sold = None
            match = re.search(r"([\d\.,]+\s*(?:mil)?)\+?\s*compras?", low)
            if match:
                sold = parse_count(match.group(1))
            delivery_node = card.select_one('[data-cy="delivery-recipe"]')

            offers.append(
                Offer(
                    marketplace="Amazon",
                    title=title,
                    price=price,
                    url=f"{BASE}/dp/{asin}",
                    shipping=0.0 if ("entrega gr" in low or "frete gr" in low) else None,
                    delivery_days=parse_days(delivery_node.get_text(" ")) if delivery_node else None,
                    product_rating=rating,
                    reviews_count=reviews,
                    sold_qty=sold,
                )
            )
            if len(offers) >= self.limit:
                break
        return offers

    def enrich(self, offer: Offer) -> Offer:
        soup, _ = self.soup(offer.url, referer=BASE + "/")
        seller_id: Optional[str] = None
        seller_name: Optional[str] = None

        node = soup.select_one("#sellerProfileTriggerId")
        if node:
            seller_name = clean_text(node.get_text(" "))
            match = re.search(r"seller=([A-Z0-9]+)", node.get("href", ""))
            seller_id = match.group(1) if match else None
        if not seller_name:
            node = soup.select_one('[tabular-attribute-name="Vendido por"], #merchant-info')
            if node:
                merchant = clean_text(node.get_text(" "))
                match = re.search(r"Vendido (?:e entregue )?por\s+(.+?)(?:\s+e\s+entregue|\.|$)", merchant, re.I)
                seller_name = clean_text(match.group(1)) if match else merchant[:60]
        if not seller_name and "entregue por amazon" in soup.get_text(" ").lower():
            seller_name = "Amazon.com.br"

        buybox = soup.select_one("#merchant-info, #tabular-buybox")
        if buybox:
            match = re.search(r"(\d{2,3})\s*%\s*(?:de\s*)?(?:avalia\w+\s*)?positiv", buybox.get_text(" "), re.I)
            if match:
                offer.seller_positive_pct = float(match.group(1))

        if seller_name:
            offer.seller = seller_name
            if "amazon" in seller_name.lower():
                offer.seller_badge = offer.seller_badge or "Vendido pela Amazon"
        if seller_id:
            offer.url = f"{offer.url}?m={seller_id}"
        return offer
