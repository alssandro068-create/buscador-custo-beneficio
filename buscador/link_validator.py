"""Garante que o link retornado é a página de uma oferta/anúncio específico.

Rejeita: home do e-commerce, páginas de busca/listagem, links de clique/tracking.
Aceita apenas URLs com o formato de página de produto de cada marketplace.
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

PRODUCT_PATTERNS = {
    # produto.mercadolivre.com.br/MLB-123456789-titulo  |  www.mercadolivre.com.br/titulo/p/MLB12345678
    "Mercado Livre": re.compile(
        r"^https://(?:produto|www)\.mercadolivre\.com\.br/.*(?:MLB-?\d{6,}|MLBU\d+)", re.I
    ),
    # www.amazon.com.br/dp/B0XXXXXXXX
    "Amazon": re.compile(r"^https://www\.amazon\.com\.br/(?:[^/?#]+/)?dp/[A-Z0-9]{10}(?:[/?#]|$)"),
    # www.magazineluiza.com.br/titulo/p/codigo/ca/categoria/
    "Magalu": re.compile(r"^https://www\.magazineluiza\.com\.br/[^?#]+/p/[a-z0-9]+/", re.I),
    # pt.aliexpress.com/item/1005001234567890.html
    "AliExpress": re.compile(r"^https://[a-z]{2,3}\.aliexpress\.com/item/\d+\.html"),
    # shopee.com.br/product/<shopid>/<itemid>  |  shopee.com.br/titulo-i.<shopid>.<itemid>
    "Shopee": re.compile(r"^https://shopee\.com\.br/(?:product/\d+/\d+|[^?#]+-i\.\d+\.\d+)"),
}


def _is_generic(url: str) -> bool:
    parsed = urlparse(url)
    host, path = parsed.netloc.lower(), parsed.path.lower()
    query = parsed.query.lower()
    if host.startswith(("lista.", "click")):
        return True
    if path in ("", "/"):
        return True
    if path == "/s" or path.startswith(("/busca/", "/wholesale", "/w/", "/search")):
        return True
    return "searchtext=" in query or ("k=" in query and path == "/s")


def is_direct_offer_url(marketplace: str, url: str) -> bool:
    """True somente se `url` for a página do produto/anúncio específico."""
    if not url or not url.startswith("https://"):
        return False
    if _is_generic(url):
        return False
    pattern = PRODUCT_PATTERNS.get(marketplace)
    return bool(pattern and pattern.search(url))
