"""Orquestra: busca -> valida links -> filtra -> pontua -> enriquece o topo -> reponta -> seleciona."""
from __future__ import annotations

import logging
from collections import Counter
from contextlib import ExitStack
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from .browser import Browser, BrowserUnavailable, playwright_available
from .filters import dedupe, filter_offers
from .http_client import BlockedError, HttpClient
from .link_validator import is_direct_offer_url
from .marketplaces import MARKETPLACES
from .models import Offer
from .scoring import score_offers

log = logging.getLogger(__name__)


@dataclass
class SearchOptions:
    lojas: List[str] = field(default_factory=lambda: list(MARKETPLACES))
    top: int = 15
    max_por_loja: Optional[int] = 6
    limite_por_loja: int = 40
    preco_min: Optional[float] = None
    preco_max: Optional[float] = None
    enriquecer: bool = True
    enriquecer_top: int = 12
    incluir_acessorios: bool = False
    incluir_usados: bool = False
    usar_playwright: bool = False


def _select(ranked: List[Offer], top: int, per_store: Optional[int]) -> List[Offer]:
    chosen: List[Offer] = []
    counts: Counter = Counter()
    for offer in ranked:
        if per_store and counts[offer.marketplace] >= per_store:
            continue
        chosen.append(offer)
        counts[offer.marketplace] += 1
        if len(chosen) >= top:
            break
    return chosen


def run_search(query: str, opts: SearchOptions) -> Tuple[List[Offer], Dict[str, Dict[str, Any]]]:
    stats: Dict[str, Dict[str, Any]] = {}
    raw: List[Offer] = []
    providers: Dict[str, Any] = {}

    with ExitStack() as stack:
        browser: Optional[Browser] = None
        needs_browser = any(MARKETPLACES[k].requires_browser for k in opts.lojas)
        if needs_browser and opts.usar_playwright:
            if not playwright_available():
                log.warning("Playwright não instalado; AliExpress/Shopee serão ignorados.")
            else:
                try:
                    browser = stack.enter_context(Browser())
                except BrowserUnavailable as exc:
                    log.warning("%s", exc)

        for key in opts.lojas:
            cls = MARKETPLACES[key]
            if cls.requires_browser and browser is None:
                stats[cls.name] = {"status": "ignorado", "encontrados": 0,
                                   "mensagem": "Requer Playwright (use --playwright)."}
                continue
            provider = cls(http=HttpClient(), browser=browser, limit=opts.limite_por_loja)
            providers[cls.name] = provider
            log.info("Buscando em %s ...", cls.name)
            try:
                found = provider.search(query)
                stats[cls.name] = {"status": "ok" if found else "sem resultados", "encontrados": len(found), "mensagem": ""}
                raw.extend(found)
            except BlockedError as exc:
                stats[cls.name] = {"status": "bloqueado", "encontrados": 0, "mensagem": str(exc)}
                log.warning("%s bloqueou a busca: %s", cls.name, exc)
            except Exception as exc:  # noqa: BLE001 - uma loja com problema não derruba as demais
                stats[cls.name] = {"status": "erro", "encontrados": 0, "mensagem": f"{type(exc).__name__}: {exc}"}
                log.warning("Erro em %s: %s", cls.name, exc)

        # 1) Só links DIRETOS de anúncio passam.
        valid: List[Offer] = []
        invalid: Counter = Counter()
        for offer in raw:
            if is_direct_offer_url(offer.marketplace, offer.url):
                valid.append(offer)
            else:
                invalid[offer.marketplace] += 1
        for name, count in invalid.items():
            stats[name]["links_descartados"] = count

        # 2) Relevância / acessórios / usados / faixa de preço.
        candidates, dropped = filter_offers(
            dedupe(valid), query,
            include_accessories=opts.incluir_acessorios,
            include_used=opts.incluir_usados,
            price_min=opts.preco_min, price_max=opts.preco_max,
        )
        if dropped:
            log.info("Descartes por filtro: %s", dropped)

        # 3) Pontuação preliminar -> enriquece só o topo (abre a página do anúncio).
        ranked = score_offers(candidates)
        if opts.enriquecer and ranked:
            blocked_stores: Set[str] = set()
            for offer in ranked[: opts.enriquecer_top]:
                provider = providers.get(offer.marketplace)
                if not provider or offer.marketplace in blocked_stores:
                    continue
                original_url = offer.url
                try:
                    provider.enrich(offer)
                except BlockedError:
                    blocked_stores.add(offer.marketplace)
                    log.warning("Enriquecimento bloqueado em %s; seguindo sem detalhes.", offer.marketplace)
                except Exception as exc:  # noqa: BLE001
                    log.debug("Falha ao enriquecer %s: %s", offer.url, exc)
                if not is_direct_offer_url(offer.marketplace, offer.url):
                    offer.url = original_url

        # 4) Pontuação final e seleção (com limite por loja p/ diversidade).
        final = score_offers(candidates)
        selected = _select(final, opts.top, opts.max_por_loja)

    in_pool = Counter(o.marketplace for o in candidates)
    in_top = Counter(o.marketplace for o in selected)
    for name, info in stats.items():
        info["apos_filtros"] = in_pool.get(name, 0)
        info["no_ranking"] = in_top.get(name, 0)
    return selected, stats
