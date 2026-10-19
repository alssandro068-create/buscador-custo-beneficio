"""Filtros de relevância: remove acessórios, usados, outliers de preço e resultados fora do tema."""
from __future__ import annotations

import re
import statistics
from collections import Counter
from typing import Dict, List, Optional, Tuple

from .models import Offer
from .utils import normalize_text, tokenize

STOPWORDS = {"de", "da", "do", "das", "dos", "para", "com", "e", "a", "o", "em", "por"}

# Palavras que quase sempre indicam acessório/peça (e não o produto em si).
ACCESSORY_WORDS = {
    "capa", "capinha", "pelicula", "protetor", "adesivo", "skin", "case", "estojo",
    "suporte", "compativel", "reposicao", "refil", "pecas",
}
USED_WORDS = {"usado", "usada", "seminovo", "seminova", "recondicionado", "recondicionada", "vitrine", "sucata", "defeito"}


def query_tokens(query: str) -> List[str]:
    return [t for t in tokenize(query) if t not in STOPWORDS and (len(t) > 1 or t.isdigit())]


def relevance(tokens: List[str], title: str) -> float:
    """Fração dos termos da busca presentes no título (com tolerância a plural)."""
    if not tokens:
        return 1.0
    norm = normalize_text(title)
    hits = 0
    for tok in tokens:
        # Números aceitam sufixo de letras ("510" casa com "510BT", "128" com "128GB"),
        # mas não mais dígitos ("15" não casa com "150").
        tail = r"(?![0-9])" if tok.isdigit() else r"s?(?![a-z0-9])"
        if re.search(rf"(?<![a-z0-9]){re.escape(tok)}{tail}", norm):
            hits += 1
    return hits / len(tokens)


def filter_offers(
    offers: List[Offer],
    query: str,
    *,
    min_relevance: float = 0.8,
    include_accessories: bool = False,
    include_used: bool = False,
    price_min: Optional[float] = None,
    price_max: Optional[float] = None,
    drop_outliers: bool = True,
) -> Tuple[List[Offer], Dict[str, int]]:
    """Retorna (ofertas_mantidas, contagem_de_descartes_por_motivo)."""
    dropped: Counter = Counter()
    tokens = query_tokens(query)
    query_words = set(tokenize(query))
    kept: List[Offer] = []

    for offer in offers:
        words = set(tokenize(offer.title))
        if offer.price <= 0:
            dropped["preço inválido"] += 1
        elif price_min is not None and offer.price < price_min:
            dropped["abaixo do preço mínimo"] += 1
        elif price_max is not None and offer.price > price_max:
            dropped["acima do preço máximo"] += 1
        elif relevance(tokens, offer.title) < min_relevance:
            dropped["fora do tema"] += 1
        elif not include_accessories and (words & ACCESSORY_WORDS) - query_words:
            dropped["acessório/peça"] += 1
        elif not include_used and (offer.condition == "used" or (words & USED_WORDS) - query_words):
            dropped["usado/recondicionado"] += 1
        else:
            kept.append(offer)

    if drop_outliers and len(kept) >= 6:
        median = statistics.median(o.price for o in kept)
        threshold = 0.35 * median  # muito abaixo da mediana = quase sempre peça/acessório/erro
        survivors = [o for o in kept if o.price >= threshold]
        dropped["preço muito abaixo da mediana"] += len(kept) - len(survivors)
        kept = survivors

    return kept, dict(dropped)


def dedupe(offers: List[Offer]) -> List[Offer]:
    seen = set()
    unique = []
    for offer in offers:
        if offer.url not in seen:
            seen.add(offer.url)
            unique.append(offer)
    return unique
