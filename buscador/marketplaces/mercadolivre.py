"""Mercado Livre (Brasil).

Estratégia:
1. API pública de busca (https://api.mercadolibre.com/sites/MLB/search). Hoje ela costuma exigir
   token: defina ML_ACCESS_TOKEN ou ML_CLIENT_ID + ML_CLIENT_SECRET (app em developers.mercadolivre.com.br).
2. Fallback: HTML de lista.mercadolivre.com.br.
O link retornado é o `permalink` do anúncio (ou o href do card), nunca a página de resultados.
"""
from __future__ import annotations

import logging
import os
import re
from typing import List, Optional
from urllib.parse import quote

from ..http_client import FetchError
from ..models import Offer
from ..utils import (
    clean_text,
    clean_url,
    jsonld_product_info,
    normalize_text,
    parse_count,
    parse_days,
    parse_rating,
)
from .base import Marketplace

log = logging.getLogger(__name__)

API = "https://api.mercadolibre.com"
SITE_ID = "MLB"
LIST_URL = "https://lista.mercadolivre.com.br/"
KEEP_PARAMS = ("pdp_filters", "wid")  # identificam a oferta específica em páginas de catálogo (/p/)


class MercadoLivre(Marketplace):
    key = "mercadolivre"
    name = "Mercado Livre"

    # ------------------------------------------------------------------ busca
    def search(self, query: str) -> List[Offer]:
        offers: List[Offer] = []
        try:
            offers = self._search_api(query)
        except FetchError as exc:
            log.info("API do Mercado Livre indisponível (%s). Usando HTML.", exc)
        if not offers:
            offers = self._search_html(query)
        return offers[: self.limit]

    def _auth_headers(self) -> dict:
        token = os.getenv("ML_ACCESS_TOKEN")
        client_id, secret = os.getenv("ML_CLIENT_ID"), os.getenv("ML_CLIENT_SECRET")
        if not token and client_id and secret:
            try:
                response = self.http.post(
                    f"{API}/oauth/token",
                    data={"grant_type": "client_credentials", "client_id": client_id, "client_secret": secret},
                    expect_json=True,
                )
                token = response.json().get("access_token")
            except (FetchError, ValueError) as exc:
                log.warning("Não foi possível obter token do Mercado Livre: %s", exc)
        return {"Authorization": f"Bearer {token}"} if token else {}

    def _search_api(self, query: str) -> List[Offer]:
        headers = self._auth_headers()
        offers: List[Offer] = []
        for offset in range(0, self.limit, 50):
            response = self.http.get(
                f"{API}/sites/{SITE_ID}/search",
                params={"q": query, "limit": min(50, self.limit - offset), "offset": offset},
                headers=headers,
                expect_json=True,
            )
            results = response.json().get("results", [])
            for item in results:
                offer = self._offer_from_api(item)
                if offer:
                    offers.append(offer)
            if len(results) < 50:
                break
        return offers

    @staticmethod
    def _offer_from_api(item: dict) -> Optional[Offer]:
        url, price = item.get("permalink"), item.get("price")
        if not url or not price:
            return None
        seller = item.get("seller") or {}
        reputation = seller.get("seller_reputation") or {}
        transactions = reputation.get("transactions") or {}
        positive = (transactions.get("ratings") or {}).get("positive")
        level = reputation.get("power_seller_status")
        shipping = item.get("shipping") or {}
        return Offer(
            marketplace="Mercado Livre",
            title=clean_text(item.get("title")),
            price=float(price),
            url=clean_url(url, KEEP_PARAMS),
            shipping=0.0 if shipping.get("free_shipping") else None,
            seller=seller.get("nickname"),
            seller_positive_pct=round(positive * 100, 1) if isinstance(positive, (int, float)) else None,
            seller_badge=f"MercadoLíder {level.capitalize()}" if level else None,
            seller_sales=transactions.get("completed"),
            sold_qty=item.get("sold_quantity"),
            condition=item.get("condition") or "new",
            official_store=bool(item.get("official_store_id")),
        )

    def _search_html(self, query: str) -> List[Offer]:
        url = LIST_URL + quote(query.strip().replace(" ", "-"))
        soup, _ = self.soup(url, referer="https://www.mercadolivre.com.br/")
        cards = soup.select("div.poly-card") or soup.select("li.ui-search-layout__item")
        offers: List[Offer] = []
        for card in cards:
            link = card.select_one("a.poly-component__title, a.ui-search-link, a.ui-search-item__group__element")
            if not link or not link.get("href"):
                continue
            title = clean_text(link.get_text(" ")) or clean_text(
                (card.select_one("h2, h3") or link).get_text(" ")
            )
            price = self._card_price(card)
            if not title or price is None:
                continue

            seller_node = card.select_one(".poly-component__seller, .ui-search-official-store-label")
            seller = re.sub(r"^\s*(?:Por|Vendido por)\s+", "", clean_text(seller_node.get_text(" ")), flags=re.I) if seller_node else None

            ship_node = card.select_one(".poly-component__shipping, .ui-search-item__shipping")
            ship_text = clean_text(ship_node.get_text(" ")) if ship_node else ""
            rating_node = card.select_one(".poly-reviews__rating, .ui-search-reviews__rating-number")
            total_node = card.select_one(".poly-reviews__total, .ui-search-reviews__amount")

            offers.append(
                Offer(
                    marketplace="Mercado Livre",
                    title=title,
                    price=price,
                    url=clean_url(link["href"], KEEP_PARAMS),
                    shipping=0.0 if "gratis" in normalize_text(ship_text) else None,
                    delivery_days=parse_days(ship_text),
                    seller=seller or None,
                    product_rating=parse_rating(rating_node.get_text()) if rating_node else None,
                    reviews_count=parse_count(total_node.get_text()) if total_node else None,
                    official_store="loja oficial" in (seller or "").lower(),
                )
            )
        return offers

    @staticmethod
    def _card_price(card) -> Optional[float]:
        for money in card.select(".andes-money-amount"):
            classes = money.get("class", [])
            if "andes-money-amount--previous" in classes or money.find_parent("s"):
                continue  # preço antigo (riscado)
            fraction = money.select_one(".andes-money-amount__fraction")
            if not fraction:
                continue
            cents = money.select_one(".andes-money-amount__cents")
            try:
                value = float(re.sub(r"\D", "", fraction.get_text()))
                if cents:
                    value += float(re.sub(r"\D", "", cents.get_text()) or 0) / 100
                return value
            except ValueError:
                continue
        return None

    # ------------------------------------------------------------- enriquecimento
    def enrich(self, offer: Offer) -> Offer:
        soup, _ = self.soup(offer.url, referer=LIST_URL)
        text = soup.get_text(" ", strip=True)
        info = jsonld_product_info(soup)

        if offer.product_rating is None:
            offer.product_rating = info.get("rating")
        if offer.reviews_count is None:
            offer.reviews_count = info.get("rating_count")

        if offer.sold_qty is None:
            match = re.search(r"([\d\.,]+\s*(?:mil)?)\s*vendidos", text, re.I)
            if match:
                offer.sold_qty = parse_count(match.group(1))

        if not offer.seller_badge:
            match = re.search(r"MercadoL[ií]der\s*(Platinum|Gold|Silver)?", text, re.I)
            if match:
                level = match.group(1)
                offer.seller_badge = f"MercadoLíder {level.capitalize()}" if level else "MercadoLíder"

        if offer.seller_sales is None:
            match = re.search(r"\+?\s*([\d\.,]+\s*(?:mil)?)\s*vendas\b", text, re.I)
            if match:
                offer.seller_sales = parse_count(match.group(1))

        if not offer.seller:
            node = soup.select_one(".ui-pdp-seller__header__title, .ui-pdp-seller__link-trigger")
            seller = info.get("seller") or (clean_text(node.get_text(" ")) if node else None)
            offer.seller = re.sub(r"^(?:Vendido por|Loja oficial)\s+", "", seller or "", flags=re.I) or None
        return offer
