import sys
import os

# Garante que o Python reconhece o diretório atual para importar o buscador
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import streamlit as st
from buscador.pipeline import SearchOptions, run_search
from buscador.report import brl

st.set_page_config(page_title="Buscador de Custo-Benefício", page_icon="🛒", layout="wide")

st.title("🛒 Buscador de Custo-Benefício")
st.write("Encontre as melhores ofertas diretamente na página do vendedor.")

query = st.text_input("Qual produto deseja pesquisar?", placeholder="Ex: iphone 15 128gb")

lojas_selecionadas = st.multiselect(
    "Selecione as lojas:",
    ["mercadolivre", "amazon", "magalu"],
    default=["mercadolivre", "amazon", "magalu"]
)

if st.button("Buscar Ofertas") and query:
    with st.spinner("Buscando as melhores ofertas..."):
        try:
            opts = SearchOptions(
                lojas=lojas_selecionadas,
                top=10,
                enriquecer=True
            )
            offers, stats = run_search(query, opts)

            if offers:
                st.success(f"Encontradas {len(offers)} ofertas para '{query}'!")
                for i, o in enumerate(offers, 1):
                    col1, col2, col3 = st.columns([3, 1, 1])
                    with col1:
                        st.markdown(f"**{i}. {o.title}**")
                        st.caption(f"Loja: {o.marketplace} | Vendedor: {o.seller or 'N/D'}")
                    with col2:
                        st.subheader(brl(o.price))
                    with col3:
                        st.link_button("Ver Oferta Direta ➔", o.url)
                    st.divider()
            else:
                st.warning("Nenhuma oferta encontrada.")
        except Exception as e:
            st.error(f"Ocorreu um erro durante a busca: {e}")
