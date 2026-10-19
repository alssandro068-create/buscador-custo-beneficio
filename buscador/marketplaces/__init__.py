"""Registro dos marketplaces suportados."""
from __future__ import annotations

from typing import Dict, Type

from .aliexpress import AliExpress
from .amazon import Amazon
from .base import Marketplace
from .magalu import Magalu
from .mercadolivre import MercadoLivre
from .shopee import Shopee

MARKETPLACES: Dict[str, Type[Marketplace]] = {
    cls.key: cls for cls in (MercadoLivre, Amazon, Magalu, AliExpress, Shopee)
}

__all__ = ["MARKETPLACES", "Marketplace"]
