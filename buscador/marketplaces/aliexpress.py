"""AliExpress (experimental): a busca é renderizada via JavaScript, então exige Playwright.

O link é normalizado para https://pt.aliexpress.com/item/<id>.html (página do anúncio).
"""
from __future__ import annotations

import re
from typing import List
from urllib.parse import quote

from bs4 import BeautifulSoup

from ..models import Offer
from ..utils import clean_text, parse_brl, parse_count
from .base import Marketplace

BASE = "https://pt.aliexpress.com"
ITEM_RE = re.compile(r"/item/(\d+)\.html")


class AliExpress(Marketplace):
    key = "aliexpress"
    name = "AliExpress"
    requires_browser = True

    def search(self, query: str) -> List[Offer]:
        html = self.browser.render(
            f"{BASE}/wholesale?SearchText={quote(query)}", wait_selector='a[href*="/item/"]'
        )
        soup = BeautifulSoup(html, "html.parser")
        offers: List[Offer] = []
        seen = set()
        for anchor in soup.select('a[href*="/item/"]'):
            match = ITEM_RE.search(anchor["href"])
            if not match or match.group(1) in seen:
                continue
            spaced = clean_text(anchor.get_text(" "))
            joined = anchor.get_text("", strip=True)  # "R$" + "12" + "," + "34" -> "R$12,34"
            price = parse_brl(joined)
            title_node = anchor.select_one("h3, [title]")
            title = clean_text(title_node.get("title") or title_node.get_text(" ")) if title_node else ""
            if not title:
                title = re.split(r"R\$", spaced, maxsplit=1)[0].strip()
            if not title or price is None:
                continue

            sold = None
            sold_match = re.search(r"([\d\.,]+\s*(?:mil)?)\+?\s*vendidos?", spaced, re.I)
            if sold_match:
                sold = parse_count(sold_match.group(1))
            store = anchor.select_one('a[href*="/store/"]')

            seen.add(match.group(1))
            offers.append(
                Offer(
                    marketplace="AliExpress",
                    title=title,
                    price=price,
                    url=f"{BASE}/item/{match.group(1)}.html",
                    shipping=0.0 if "frete gr" in spaced.lower() else None,
                    seller=clean_text(store.get_text(" ")) if store else None,
                    sold_qty=sold,
                )
            )
            if len(offers) >= self.limit:
                break
        return offers
