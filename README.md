# 🛒 Buscador de Custo-Benefício (Mercado Livre, Amazon, Magalu, AliExpress, Shopee)

Digite o nome de um produto e o projeto busca em vários marketplaces, **descarta resultados que não são
a página de um anúncio específico**, calcula um **score de custo-benefício** (preço + frete, reputação do
vendedor, volume de vendas/avaliações e prazo) e gera `RESULTADOS.md` e `resultados.json`.

> **Regra dos links:** só entram no resultado URLs com formato de página de produto/oferta
> (ex.: `produto.mercadolivre.com.br/MLB-…`, `amazon.com.br/dp/<ASIN>`, `magazineluiza.com.br/…/p/<código>/`,
> `aliexpress.com/item/<id>.html`, `shopee.com.br/product/<loja>/<item>`). Home, busca, listagens e links de
> tracking são rejeitados por `buscador/link_validator.py` (coberto por testes).

## ⚠️ Leia antes: limitações reais

- **Scraping é frágil.** Os sites mudam o HTML sem aviso. Os seletores foram escritos a partir da estrutura
  conhecida de cada site, mas **não foram validados contra os sites reais** durante a criação (o ambiente de
  desenvolvimento não tinha internet). Os testes usam HTML sintético. Se uma loja retornar `0 resultados`,
  salve o HTML real e ajuste os seletores no arquivo da loja em `buscador/marketplaces/`.
- **GitHub Actions usa IPs de datacenter**, que Amazon, Shopee, AliExpress e às vezes Magalu bloqueiam
  (CAPTCHA/403). O relatório mostra o status de cada loja (`ok`, `bloqueado`, `erro`, `ignorado`). Rodar **na sua
  máquina** (IP residencial) costuma funcionar bem melhor.
- **Mercado Livre:** a API de busca hoje costuma exigir token. Crie um app em
  <https://developers.mercadolivre.com.br> e guarde `ML_CLIENT_ID` e `ML_CLIENT_SECRET` (ou `ML_ACCESS_TOKEN`).
  Sem credenciais, o projeto usa o HTML público como fallback.
- **AliExpress e Shopee** exigem navegador real (Playwright) e são **experimentais**.
- **Reputação do vendedor** só é pública em parte dos sites (Mercado Livre é o mais completo). Nos demais, o
  score usa a nota do anúncio como aproximação e marca `n/d` no que não foi informado.
- Respeite os Termos de Uso de cada site. Para uso intensivo/comercial, prefira as APIs oficiais
  (Mercado Livre API, Amazon PA-API, AliExpress/Shopee Affiliate APIs).

## 📁 Estrutura

```
buscador-custo-beneficio/
├── .github/workflows/search.yml     # execução via GitHub Actions (workflow_dispatch)
├── buscador/
│   ├── __init__.py
│   ├── config.py                    # pesos do score, User-Agents, timeouts
│   ├── models.py                    # dataclass Offer
│   ├── utils.py                     # parsing de preço/contagem/nota, limpeza de URL, JSON-LD
│   ├── http_client.py               # headers realistas, UA rotativo, retries, detecção de bloqueio
│   ├── browser.py                   # Playwright (opcional)
│   ├── link_validator.py            # garante link direto de oferta
│   ├── filters.py                   # relevância, acessórios, usados, outliers, faixa de preço
│   ├── scoring.py                   # score de custo-benefício
│   ├── pipeline.py                  # orquestração
│   ├── report.py                    # RESULTADOS.md e resultados.json
│   └── marketplaces/
│       ├── __init__.py              # registro das lojas
│       ├── base.py
│       ├── mercadolivre.py
│       ├── amazon.py
│       ├── magalu.py
│       ├── aliexpress.py            # experimental (Playwright)
│       └── shopee.py                # experimental (Playwright)
├── tests/                           # testes (pytest)
├── main.py                          # CLI
├── requirements.txt
├── requirements-dev.txt
├── pytest.ini
├── .gitignore
└── README.md
```

## 🚀 Passo a passo: colocar no seu GitHub

**Opção A — linha de comando (recomendada; preserva a pasta `.github`)**

1. Crie um repositório vazio no GitHub (ex.: `buscador-custo-beneficio`), **sem** README inicial.
2. Descompacte o projeto, entre na pasta e rode:
   ```bash
   git init
   git add .
   git commit -m "Primeira versão"
   git branch -M main
   git remote add origin https://github.com/SEU_USUARIO/buscador-custo-beneficio.git
   git push -u origin main
   ```

**Opção B — pelo navegador**

1. No repositório: **Add file → Upload files** e arraste todas as pastas e arquivos
   (no macOS/Windows a pasta `.github` fica oculta; se não aparecer, use a Opção A).
2. Para criar só o workflow: **Add file → Create new file**, digite o nome
   `.github/workflows/search.yml` (as barras criam as pastas) e cole o conteúdo do arquivo.

**Permissão para salvar os resultados no repositório** (necessária só se marcar "commit_resultados"):
*Settings → Actions → General → Workflow permissions → Read and write permissions → Save.*

**(Opcional) Credenciais do Mercado Livre:** *Settings → Secrets and variables → Actions → New repository secret*
→ crie `ML_CLIENT_ID` e `ML_CLIENT_SECRET`.

## ▶️ Como buscar um produto

### Pelo GitHub Actions
1. Aba **Actions** → workflow **Buscar melhor custo-benefício** → **Run workflow**.
2. Preencha `produto` (ex.: `iphone 15 128gb`), escolha as lojas e, se quiser, faixa de preço.
   Marque `usar_playwright` para tentar AliExpress/Shopee (mais lento).
3. Ao terminar, veja o resultado: no **resumo do job** (tabela renderizada), no **artefato `resultados`**
   e, se marcado, nos arquivos `RESULTADOS.md` / `resultados.json` commitados no repositório.

### Na sua máquina
```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m playwright install chromium                  # só se for usar AliExpress/Shopee

python main.py "iphone 15 128gb"
python main.py "fone jbl tune 510" --lojas mercadolivre,amazon --top 10 --preco-max 400
python main.py "air fryer 5l" --playwright --lojas todas
```

Principais opções: `--lojas`, `--top`, `--max-por-loja`, `--preco-min`, `--preco-max`,
`--sem-enriquecimento` (não abre as páginas dos anúncios: mais rápido, menos dados),
`--incluir-acessorios`, `--incluir-usados`, `--playwright`, `--saida`, `-v`.

## ⚖️ Como o score funciona

Score (0–100) = **preço+frete 45%** · **reputação 25%** · **popularidade 20%** · **entrega 10%**.

- **Preço:** `(referência / (preço+frete))²`, com a referência no 10º percentil dos totais (um outlier barato
  não distorce o resto). Frete desconhecido é estimado pela mediana dos fretes conhecidos, nunca tratado como grátis.
- **Reputação:** média de % de avaliações positivas, nota do vendedor e selos (MercadoLíder Platinum/Gold,
  Loja Oficial). Sem dados do vendedor, usa a nota do anúncio com ajuste bayesiano e leve desconto.
- **Popularidade:** 60% volume (log de vendas/avaliações) + 40% nota do anúncio.
- **Entrega:** `1 − dias/21`. Prazo desconhecido recebe valor neutro baixo.

Ajuste sem mexer no código, via variáveis de ambiente (normalizadas automaticamente):
`PESO_PRECO`, `PESO_REPUTACAO`, `PESO_POPULARIDADE`, `PESO_ENTREGA`.
Ex.: `PESO_PRECO=0.6 PESO_REPUTACAO=0.3 python main.py "monitor 24"`.

## 🧪 Testes

```bash
pip install -r requirements-dev.txt
pytest
```

## ➕ Adicionar outra loja

Crie `buscador/marketplaces/minhaloja.py` com uma classe que herde de `Marketplace`, implemente `search()`
(e opcionalmente `enrich()`), registre-a em `marketplaces/__init__.py` e adicione o padrão de URL de produto
em `link_validator.PRODUCT_PATTERNS`.
