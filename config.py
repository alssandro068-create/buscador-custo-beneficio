"""Configurações globais: pesos do score, User-Agents, timeouts."""
from __future__ import annotations

import os
from typing import Dict

# User-Agents de navegadores reais e recentes. Um é sorteado por sessão HTTP
# (e trocado se o site começar a bloquear).
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "Version/17.4 Safari/605.1.15",
]

# Subconjunto usado pelo Playwright (Chromium precisa de UA no formato Chrome).
CHROME_USER_AGENTS = [ua for ua in USER_AGENTS if "Chrome/" in ua]

# Rede
REQUEST_TIMEOUT = 25
MIN_DELAY = 1.0   # pausa mínima entre requisições (segundos)
MAX_DELAY = 2.5   # pausa máxima
MAX_RETRIES = 3

# Marketplaces disponíveis (ordem padrão de execução)
DEFAULT_MARKETPLACES = ["mercadolivre", "amazon", "magalu", "aliexpress", "shopee"]

# Pesos do score de custo-benefício (somam 1.0 após normalização).
DEFAULT_WEIGHTS: Dict[str, float] = {
    "preco": 0.45,         # preço do produto + frete
    "reputacao": 0.25,     # nota/% positivas do vendedor, selos (MercadoLíder etc.)
    "popularidade": 0.20,  # volume de vendas/avaliações + nota do anúncio
    "entrega": 0.10,       # prazo estimado (quando disponível)
}

# Valor neutro (abaixo de 0.5, para não premiar quem não informa o dado)
# usado quando a informação não está disponível no marketplace.
NEUTRAL = {"reputacao": 0.40, "popularidade": 0.30, "entrega": 0.40}

# Volume (vendas ou avaliações) a partir do qual a popularidade satura em 1.0
VOLUME_REFERENCE = 1000


def load_weights() -> Dict[str, float]:
    """Lê pesos de variáveis de ambiente (PESO_PRECO, PESO_REPUTACAO, ...) e normaliza."""
    weights = {}
    for key, default in DEFAULT_WEIGHTS.items():
        raw = os.getenv(f"PESO_{key.upper()}")
        try:
            weights[key] = float(raw) if raw else default
        except ValueError:
            weights[key] = default
    total = sum(weights.values()) or 1.0
    return {k: v / total for k, v in weights.items()}
