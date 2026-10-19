"""Modelo de dados de uma oferta (anúncio de um vendedor específico)."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Optional


@dataclass
class Offer:
    marketplace: str
    title: str
    price: float
    url: str  # URL DIRETA do anúncio/oferta (nunca página de busca ou home)

    shipping: Optional[float] = None        # None = desconhecido | 0.0 = grátis
    delivery_days: Optional[int] = None

    seller: Optional[str] = None
    seller_rating: Optional[float] = None       # 0-5
    seller_positive_pct: Optional[float] = None  # 0-100
    seller_badge: Optional[str] = None           # ex.: "MercadoLíder Platinum"
    seller_sales: Optional[int] = None

    sold_qty: Optional[int] = None          # vendas do anúncio
    reviews_count: Optional[int] = None     # nº de avaliações do anúncio
    product_rating: Optional[float] = None  # nota do anúncio (0-5)

    condition: str = "new"
    official_store: bool = False

    score: float = 0.0
    score_breakdown: Dict[str, Any] = field(default_factory=dict)

    @property
    def total_known(self) -> float:
        """Preço + frete (frete desconhecido conta como 0 aqui; o score usa estimativa)."""
        return self.price + (self.shipping or 0.0)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["total_conhecido"] = round(self.total_known, 2)
        return data
