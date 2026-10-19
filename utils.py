"""Funções utilitárias: normalização de texto, parsing de preços/contagens, URLs, JSON-LD."""
from __future__ import annotations

import json
import re
import unicodedata
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import parse_qs, parse_qsl, unquote, urlencode, urlparse, urlunparse


def normalize_text(text: Optional[str]) -> str:
    """Minúsculas e sem acentos."""
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    return text.lower().strip()


def tokenize(text: Optional[str]) -> List[str]:
    return re.findall(r"[a-z0-9]+", normalize_text(text))


def clean_text(text: Optional[str]) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


_PRICE_RE = re.compile(r"R\$\s*([\d\.]+(?:,\d{1,2})?)")
_BARE_PRICE_RE = re.compile(r"^\s*([\d\.]+(?:,\d{1,2})?)\s*$")


def parse_brl(text: Optional[str]) -> Optional[float]:
    """'R$ 1.299,90' -> 1299.9 | '1.299' -> 1299.0 (primeiro valor encontrado)."""
    if not text:
        return None
    match = _PRICE_RE.search(text) or _BARE_PRICE_RE.match(text)
    if not match:
        return None
    raw = match.group(1).replace(".", "").replace(",", ".")
    try:
        return float(raw)
    except ValueError:
        return None


def parse_count(text: Optional[str]) -> Optional[int]:
    """'1,5 mil' -> 1500 | '+500' -> 500 | '(1.234)' -> 1234 | '2 mi' -> 2000000."""
    if not text:
        return None
    match = re.search(r"(\d[\d\.,]*)\s*(mil\b|k\b|mi\b|milh)?", text.lower())
    if not match:
        return None
    number, suffix = match.group(1), match.group(2)
    multiplier = 1
    if suffix in ("mil", "k"):
        multiplier = 1_000
    elif suffix:
        multiplier = 1_000_000
    try:
        if multiplier > 1:
            norm = number.replace(".", "").replace(",", ".") if "," in number else number
            return int(round(float(norm) * multiplier))
        return int(re.sub(r"[\.,]", "", number))
    except ValueError:
        return None


def parse_rating(text: Optional[str]) -> Optional[float]:
    """'4,5 de 5 estrelas' -> 4.5 (limitado a 0-5)."""
    if not text:
        return None
    match = re.search(r"(\d+(?:[.,]\d+)?)", text)
    if not match:
        return None
    value = float(match.group(1).replace(",", "."))
    return value if 0 <= value <= 5 else None


def parse_days(text: Optional[str]) -> Optional[int]:
    """Estima prazo em dias a partir de textos como 'Chegará amanhã' ou '3 a 5 dias úteis'."""
    low = normalize_text(text)
    if not low:
        return None
    if "hoje" in low:
        return 0
    if "amanha" in low:
        return 1
    match = re.search(r"(\d+)\s*(?:a\s*(\d+)\s*)?dias", low)
    if match:
        return int(match.group(2) or match.group(1))
    return None


def to_float(value: Any) -> Optional[float]:
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None


def to_int(value: Any) -> Optional[int]:
    try:
        return int(float(str(value).replace(",", ".")))
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------- URLs
def unwrap_tracking_url(url: str) -> str:
    """Desembrulha links de clique/anúncio (ex.: click1.mercadolivre.com.br/...&url=<destino>)."""
    parsed = urlparse(url)
    if "click" not in parsed.netloc and "/click" not in parsed.path:
        return url
    query = parse_qs(parsed.query)
    for key in ("url", "u", "redirect", "target"):
        values = query.get(key)
        if values and values[0].startswith("http"):
            return unquote(values[0])
    return url


def clean_url(url: str, keep_params: Iterable[str] = ()) -> str:
    """Remove fragmento e parâmetros de rastreio, mantendo só os parâmetros desejados."""
    parsed = urlparse(unwrap_tracking_url(url))
    keep = set(keep_params)
    query = [(k, v) for k, v in parse_qsl(parsed.query) if k in keep]
    return urlunparse((parsed.scheme or "https", parsed.netloc, parsed.path, "", urlencode(query), ""))


# ---------------------------------------------------------------- JSON-LD
def extract_jsonld(soup) -> List[Dict[str, Any]]:
    """Retorna todos os objetos JSON-LD (inclusive os dentro de @graph) de uma página."""
    found: List[Dict[str, Any]] = []
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or tag.get_text() or "")
        except ValueError:
            continue
        stack = [data]
        while stack:
            current = stack.pop()
            if isinstance(current, list):
                stack.extend(current)
            elif isinstance(current, dict):
                found.append(current)
                graph = current.get("@graph")
                if isinstance(graph, list):
                    stack.extend(graph)
    return found


def jsonld_product_info(soup) -> Dict[str, Any]:
    """Extrai nota, nº de avaliações e vendedor do JSON-LD de um Product, se existir."""
    info: Dict[str, Any] = {}
    for item in extract_jsonld(soup):
        types = item.get("@type")
        types = types if isinstance(types, list) else [types]
        if "Product" not in types:
            continue
        agg = item.get("aggregateRating")
        if isinstance(agg, dict):
            info.setdefault("rating", to_float(agg.get("ratingValue")))
            info.setdefault("rating_count", to_int(agg.get("ratingCount") or agg.get("reviewCount")))
        offers = item.get("offers")
        if isinstance(offers, list):
            offers = offers[0] if offers else {}
        if isinstance(offers, dict):
            seller = offers.get("seller")
            if isinstance(seller, dict):
                info.setdefault("seller", seller.get("name"))
            elif isinstance(seller, str):
                info.setdefault("seller", seller)
    return {k: v for k, v in info.items() if v is not None}
