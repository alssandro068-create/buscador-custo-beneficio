"""Score de custo-benefício (0-100).

Componentes (cada um normalizado em 0..1, depois ponderado por `config.DEFAULT_WEIGHTS`):

* preço        -> (referência_p10 / (preço + frete)) ** 2. Referência = 10º percentil dos totais,
                  então um único outlier barato não "achata" todos os outros.
* reputação    -> média de: % de avaliações positivas (80%→0, 100%→1), nota do vendedor (3→0, 5→1)
                  e selos (MercadoLíder Platinum/Gold, Loja Oficial...). Sem dados do vendedor,
                  usa a nota do anúncio (com ajuste bayesiano) como proxy, com leve desconto.
* popularidade -> 60% volume (log de vendas/avaliações, saturando em VOLUME_REFERENCE) +
                  40% qualidade (nota do anúncio com ajuste bayesiano p/ poucas avaliações).
* entrega      -> 1 - dias/21 (prazo desconhecido recebe valor neutro).

Dados ausentes recebem valor neutro (< 0.5) para não premiar quem não informa.
"""
from __future__ import annotations

import math
import statistics
from typing import Dict, List, Optional, Tuple

from .config import NEUTRAL, VOLUME_REFERENCE, load_weights
from .models import Offer
from .utils import normalize_text


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _percentile(values: List[float], q: float) -> float:
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    pos = (len(ordered) - 1) * q
    lower, upper = math.floor(pos), math.ceil(pos)
    if lower == upper:
        return ordered[int(pos)]
    return ordered[lower] * (upper - pos) + ordered[upper] * (pos - lower)


def bayes_rating(rating: float, count: Optional[int], prior: float = 4.0, weight: int = 10) -> float:
    """Puxa notas com poucas avaliações em direção à média (4.0)."""
    n = count or 0
    return (rating * n + prior * weight) / (n + weight)


def badge_score(offer: Offer) -> Optional[float]:
    scores = []
    badge = normalize_text(offer.seller_badge)
    if "platinum" in badge:
        scores.append(1.0)
    elif "gold" in badge:
        scores.append(0.9)
    elif "silver" in badge or "lider" in badge:
        scores.append(0.8)
    elif any(word in badge for word in ("oficial", "verificado", "mall", "preferido")):
        scores.append(0.9)
    if offer.official_store:
        scores.append(0.9)
    return max(scores) if scores else None


def reputation_score(offer: Offer) -> Tuple[float, str]:
    parts = []
    if offer.seller_positive_pct is not None:
        parts.append(_clamp((offer.seller_positive_pct - 80.0) / 20.0))
    if offer.seller_rating is not None:
        parts.append(_clamp((offer.seller_rating - 3.0) / 2.0))
    badge = badge_score(offer)
    if badge is not None:
        parts.append(badge)
    if parts:
        return sum(parts) / len(parts), "vendedor"
    if offer.product_rating is not None:
        adjusted = bayes_rating(offer.product_rating, offer.reviews_count)
        return _clamp((adjusted - 3.0) / 2.0) * 0.9, "nota do anúncio (proxy)"
    return NEUTRAL["reputacao"], "desconhecida"


def popularity_score(offer: Offer) -> float:
    has_volume = offer.sold_qty is not None or offer.reviews_count is not None
    volume = None
    if has_volume:
        vol = max(offer.sold_qty or 0, offer.reviews_count or 0)
        volume = _clamp(math.log1p(vol) / math.log1p(VOLUME_REFERENCE))
    quality = None
    if offer.product_rating is not None:
        quality = _clamp((bayes_rating(offer.product_rating, offer.reviews_count) - 3.0) / 2.0)

    if volume is None and quality is None:
        return NEUTRAL["popularidade"]
    if volume is None:
        return 0.5 * quality + 0.5 * NEUTRAL["popularidade"]
    if quality is None:
        return volume
    return 0.6 * volume + 0.4 * quality


def delivery_score(offer: Offer) -> float:
    if offer.delivery_days is None:
        return NEUTRAL["entrega"]
    return _clamp(1.0 - offer.delivery_days / 21.0)


def score_offers(offers: List[Offer], weights: Optional[Dict[str, float]] = None) -> List[Offer]:
    """Calcula `score` e `score_breakdown` de cada oferta e devolve a lista ordenada (melhor primeiro)."""
    if not offers:
        return []
    weights = weights or load_weights()

    known_shipping = [o.shipping for o in offers if o.shipping is not None]
    assumed_shipping = statistics.median(known_shipping) if known_shipping else 0.0

    totals = [o.price + (o.shipping if o.shipping is not None else assumed_shipping) for o in offers]
    reference = _percentile(totals, 0.10)

    for offer, total in zip(offers, totals):
        price_s = _clamp(reference / total) ** 2 if total > 0 else 0.0
        rep_s, rep_source = reputation_score(offer)
        pop_s = popularity_score(offer)
        del_s = delivery_score(offer)

        final = (
            weights["preco"] * price_s
            + weights["reputacao"] * rep_s
            + weights["popularidade"] * pop_s
            + weights["entrega"] * del_s
        )
        offer.score = round(final * 100, 1)
        offer.score_breakdown = {
            "preco": round(price_s, 3),
            "reputacao": round(rep_s, 3),
            "popularidade": round(pop_s, 3),
            "entrega": round(del_s, 3),
            "fonte_reputacao": rep_source,
            "total_considerado": round(total, 2),
            "frete_estimado": offer.shipping is None,
        }

    return sorted(offers, key=lambda o: (-o.score, o.score_breakdown["total_considerado"]))
