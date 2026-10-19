"""Geração de RESULTADOS.md e resultados.json."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from .models import Offer


def brl(value: float) -> str:
    return "R$ " + f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _esc(text: Optional[str]) -> str:
    return (text or "").replace("|", "\\|").replace("\n", " ").strip()


def _short(text: str, size: int = 90) -> str:
    return text if len(text) <= size else text[: size - 1].rstrip() + "…"


def _link(url: str) -> str:
    return url.replace("(", "%28").replace(")", "%29")


def format_shipping(offer: Offer) -> str:
    if offer.shipping is None:
        return "n/d"
    return "Grátis" if offer.shipping == 0 else brl(offer.shipping)


def format_total(offer: Offer) -> str:
    if offer.shipping is None:
        return f"{brl(offer.price)} + frete n/d"
    return brl(offer.price + offer.shipping)


def format_reputation(offer: Offer) -> str:
    parts = []
    if offer.seller_badge:
        parts.append(offer.seller_badge)
    if offer.seller_positive_pct is not None:
        parts.append(f"{offer.seller_positive_pct:.0f}% positivas")
    if offer.seller_rating is not None:
        parts.append(f"★{offer.seller_rating:.1f} vendedor")
    if offer.product_rating is not None:
        parts.append(f"★{offer.product_rating:.1f} anúncio")
    return " · ".join(parts) or "n/d"


def format_volume(offer: Offer) -> str:
    parts = []
    if offer.sold_qty is not None:
        parts.append(f"{offer.sold_qty:,}".replace(",", ".") + " vendidos")
    if offer.reviews_count is not None:
        parts.append(f"{offer.reviews_count:,}".replace(",", ".") + " aval.")
    return " / ".join(parts) or "n/d"


def _now_br() -> str:
    return datetime.now(timezone(timedelta(hours=-3))).strftime("%d/%m/%Y %H:%M (UTC-3)")


def write_markdown(path: str, query: str, offers: List[Offer], stats: Dict[str, Dict[str, Any]],
                   weights: Dict[str, float]) -> None:
    lines: List[str] = [f"# 🛒 Melhores ofertas para: {_esc(query)}", "", f"_Gerado em {_now_br()}_", ""]

    if offers:
        best = offers[0]
        lines += [
            "## 🏆 Melhor custo-benefício", "",
            f"**{_esc(_short(best.title))}** — {best.marketplace}"
            f"{' — vendedor ' + _esc(best.seller) if best.seller else ''}  ",
            f"Total: {format_total(best)} · Score: **{best.score:.1f}/100** · "
            f"[Ir direto para a oferta]({_link(best.url)})", "",
        ]
    else:
        lines += ["> Nenhuma oferta válida encontrada. Veja a seção *Status por marketplace* abaixo.", ""]

    lines += [
        "## 📊 Tabela comparativa", "",
        "| # | Produto / Anúncio | Loja | Preço | Frete | Total | Vendedor | Reputação / Nota | Vendas / Aval. | Score | Link direto |",
        "|--:|---|---|--:|--:|--:|---|---|---|--:|---|",
    ]
    for i, o in enumerate(offers, 1):
        lines.append(
            f"| {i} | {_esc(_short(o.title))} | {o.marketplace} | {brl(o.price)} | {format_shipping(o)} | "
            f"{_esc(format_total(o))} | {_esc(o.seller) or 'n/d'} | {_esc(format_reputation(o))} | "
            f"{format_volume(o)} | **{o.score:.1f}** | [Abrir oferta]({_link(o.url)}) |"
        )

    if offers:
        lines += ["", "## 🔗 Links diretos das ofertas", ""]
        for i, o in enumerate(offers, 1):
            lines.append(f"{i}. {o.marketplace} — <{o.url}>")

    lines += ["", "## 📡 Status por marketplace", "",
              "| Marketplace | Status | Encontrados | Após filtros | No ranking | Observação |",
              "|---|---|--:|--:|--:|---|"]
    for name, info in stats.items():
        note = _esc(info.get("mensagem", ""))
        if info.get("links_descartados"):
            note = (note + " " if note else "") + f"{info['links_descartados']} link(s) descartado(s) por não serem página de oferta."
        lines.append(
            f"| {name} | {info['status']} | {info.get('encontrados', 0)} | "
            f"{info.get('apos_filtros', 0)} | {info.get('no_ranking', 0)} | {note} |"
        )

    lines += [
        "", "## ⚖️ Como o score é calculado", "",
        f"Score (0–100) = preço+frete **{weights['preco']:.0%}** · reputação do vendedor **{weights['reputacao']:.0%}** · "
        f"popularidade (vendas/avaliações/nota) **{weights['popularidade']:.0%}** · prazo de entrega **{weights['entrega']:.0%}**.", "",
        "- `n/d` = o marketplace não informou o dado na busca; nesses casos o score usa um valor neutro (baixo) "
        "e, para frete desconhecido, estima a mediana dos fretes conhecidos.",
        "- Na Amazon, Shopee e AliExpress a reputação do vendedor raramente é pública; usa-se a nota do anúncio como aproximação.",
        "- Preços e estoques mudam a todo momento: confirme valor, frete e prazo na tela de finalização da compra.", "",
    ]
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))


def write_json(path: str, query: str, offers: List[Offer], stats: Dict[str, Dict[str, Any]],
               weights: Dict[str, float]) -> None:
    payload = {
        "consulta": query,
        "gerado_em": _now_br(),
        "pesos": {k: round(v, 4) for k, v in weights.items()},
        "status_lojas": stats,
        "resultados": [o.to_dict() for o in offers],
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
