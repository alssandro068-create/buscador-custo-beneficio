"""Magazine Luiza (Magalu). O link é o href do card de produto (…/p/<código>/…).

O Magalu usa proteção anti-bot; se bloquear, o status aparece no relatório.
"""
from __future__ import annotations

import re
from typing import List
from urllib.parse import quote, urljoin

from ..models import Offer
from ..utils import clean_text, clean_url, jsonld_product_info, parse_brl, parse_count, parse_rating
from .base import Marketplace

BASE = "https://www.magazineluiza.com.br"
PRODUCT_PATH = re.compile(r"/p/[a-z0-9]+/", re.I)
KEEP_PARAMS = ("seller_id",)


class Magalu(Marketplace):
    key = "magalu"
    name = "Magalu"

    def search(self, query: str) -> List[Offer]:
        soup, _ = self.soup(f"{BASE}/busca/{quote(query.strip())}/", referer=BASE + "/")
        anchors = soup.select('a[data-testid="product-card-container"]')
        if not anchors:  # fallback: qualquer link com cara de página de produto
            anchors = [a for a in soup.select("a[href]") if PRODUCT_PATH.search(a["href"])]

        offers: List[Offer] = []
        seen = set()
        for anchor in anchors:
            url = clean_url(urljoin(BASE, anchor["href"]), KEEP_PARAMS)
            if url in seen:
                continue
            card = anchor if anchor.get("data-testid") == "product-card-container" else (anchor.find_parent("li") or anchor)

            title_node = card.select_one('[data-testid="product-title"]') or card.select_one("h2, h3")
            title = clean_text(title_node.get_text(" ")) if title_node else clean_text(anchor.get("title"))
            price_node = card.select_one('[data-testid="price-value"]')
            price = parse_brl((price_node or card).get_text(" "))
            if not title or price is None:
                continue

            rating, reviews = None, None
            review_node = card.select_one('[data-testid="review"]')
            if review_node:
                match = re.search(r"(\d[.,]\d)\s*\(?\s*([\d\.]+)?", review_node.get_text(" "))
                if match:
                    rating = parse_rating(match.group(1))
                    reviews = parse_count(match.group(2)) if match.group(2) else None

            seen.add(url)
            offers.append(
                Offer(
                    marketplace="Magalu",
                    title=title,
                    price=price,
                    url=url,
                    product_rating=rating,
                    reviews_count=reviews,
                )
            )
            if len(offers) >= self.limit:
                break
        return offers

    def enrich(self, offer: Offer) -> Offer:
        soup, _ = self.soup(offer.url, referer=BASE + "/")
        info = jsonld_product_info(soup)
        if offer.product_rating is None:
            offer.product_rating = info.get("rating")
        if offer.reviews_count is None:
            offer.reviews_count = info.get("rating_count")

        seller = info.get("seller")
        if not seller:
            text = soup.get_text("\n", strip=True)
            match = re.search(r"Vendid[oa](?: e entregue)? por\s*\n?\s*([^\n]{2,60})", text, re.I)
            seller = clean_text(match.group(1)).rstrip(".") if match else None
        if seller:
            offer.seller = seller
            if "magalu" in seller.lower() or "magazine" in seller.lower():
                offer.seller_badge = offer.seller_badge or "Loja Oficial Magalu"
                offer.official_store = True
        return offer
