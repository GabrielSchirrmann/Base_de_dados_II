# -*- coding: utf-8 -*-
"""
Dashboard de imoveis (Sinop).
Rodar com:  python -m streamlit run dashboard.py
"""
import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text

# Faixas plausiveis (mesmas do scraper) — usadas para flagar valores suspeitos
FAIXAS_VALOR = {
    "venda": {
        "casa":(50_000,20_000_000), "apartamento":(50_000,20_000_000),
        "kitnet":(40_000,2_000_000), "terreno":(20_000,30_000_000),
        "sala":(30_000,10_000_000), "galpao":(80_000,50_000_000),
        "barracao":(80_000,50_000_000), "loja":(50_000,20_000_000),
        "*":(20_000,50_000_000),
    },
    "aluguel": {
        "casa":(300,50_000), "apartamento":(300,30_000),
        "kitnet":(200,10_000), "terreno":(200,50_000),
        "sala":(300,50_000), "galpao":(500,200_000),
        "barracao":(500,200_000), "loja":(300,100_000),
        "*":(200,200_000),
    },
}

def _faixa(mod, tipo):
    m = FAIXAS_VALOR.get(mod, {})
    return m.get(tipo) or m.get("*") or (1, 1e12)

def _suspeito(row):
    if pd.isna(row.get("valor")): return True
    lo, hi = _faixa(row.get("modalidade", ""), row.get("tipo", ""))
    return not (lo <= row["valor"] <= hi)

# ── Banco ──────────────────────────────────────────────────────────────────────
USERNAME = "root"
PASSWORD = "OnPc1071!"
HOST     = "localhost"
PORT     = 3306
DATABASE = "imobiliaria"

@st.cache_resource
def get_engine():
    return create_engine(
        f"mysql+pymysql://{USERNAME}:{PASSWORD}@{HOST}:{PORT}/{DATABASE}?charset=utf8mb4"
    )

@st.cache_data(ttl=300)
def carregar_dados() -> pd.DataFrame:
    with get_engine().connect() as conn:
        df = pd.read_sql(text("SELECT * FROM imoveis"), conn)
    if "url" in df.columns:
        df = df.drop_duplicates(subset=["url"], keep="last")
    return df

# ── Pagina ─────────────────────────────────────────────────────────────────────
st.set_page_config(page_title="Imoveis Sinop", page_icon="🏠", layout="wide")

st.title("🏠 Dashboard de Imoveis — Sinop")
st.caption("Dados coletados via web scraping da Meta Imobiliaria.")

df = carregar_dados()
if df.empty:
    st.warning("Nenhum imovel no banco. Rode o scraper primeiro.")
    st.stop()

# Marca registros suspeitos (valor fora da faixa plausivel para o tipo/modalidade)
df["suspeito"] = df.apply(_suspeito, axis=1)

# ── Filtros ───────────────────────────────────────────────────────────────────
st.sidebar.header("Filtros")

# 1) Ordenacao por valor
ordem = st.sidebar.radio(
    "Ordenar por valor",
    ["Decrescente", "Crescente"],
    horizontal=True,
)

# 2) Bairro
bairros = sorted([b for b in df["bairro"].dropna().unique() if b.strip()])
bairro_sel = st.sidebar.multiselect(
    "Bairro", bairros, default=[],
    placeholder="Todos os bairros",
)

# 3) Categoria (modalidade: venda / aluguel)
modalidades = sorted([m for m in df["modalidade"].dropna().unique() if m.strip()])
modalidade_sel = st.sidebar.multiselect(
    "Categoria", modalidades, default=modalidades,
)

# 4) Tipo (casa, apartamento, kitnet, terreno, etc)
tipos = sorted([t for t in df["tipo"].dropna().unique() if t.strip()])
tipo_sel = st.sidebar.multiselect(
    "Tipo", tipos, default=tipos,
)

n_suspeitos = int(df["suspeito"].sum())
if n_suspeitos:
    st.sidebar.caption(f"⚠️ {n_suspeitos} registro(s) com valor suspeito (ver aba 'Possiveis erros').")

# ── Aplicar filtros (apenas para a aba principal) ─────────────────────────────
def aplicar_filtros(base: pd.DataFrame) -> pd.DataFrame:
    out = base.copy()
    if bairro_sel:
        out = out[out["bairro"].isin(bairro_sel)]
    if modalidade_sel:
        out = out[out["modalidade"].isin(modalidade_sel)]
    if tipo_sel:
        out = out[out["tipo"].isin(tipo_sel)]
    return out.sort_values("valor", ascending=(ordem == "Crescente"), na_position="last")

# ── Colunas padrao para tabela ────────────────────────────────────────────────
COLUNAS = [
    "modalidade", "tipo", "bairro", "cidade", "valor",
    "area_total", "area_construida",
    "quantidade_quartos", "quantidade_banheiros", "quantidade_vagas",
    "data_coleta", "url",
]
COL_CONFIG = {
    "valor": st.column_config.NumberColumn("Valor (R$)", format="R$ %.2f"),
    "url":   st.column_config.LinkColumn("Link"),
    "modalidade": "Categoria",
    "tipo": "Tipo",
    "bairro": "Bairro",
    "cidade": "Cidade",
    "area_total": "Area total",
    "area_construida": "Area construida",
    "quantidade_quartos":   "Quartos",
    "quantidade_banheiros": "Banheiros",
    "quantidade_vagas":     "Vagas",
    "data_coleta": "Coleta",
}

# ── Abas ──────────────────────────────────────────────────────────────────────
tab_main, tab_erros = st.tabs(["📊 Imoveis", f"⚠️ Possiveis erros ({n_suspeitos})"])

with tab_main:
    # So mostra os "limpos" aqui
    base = df[~df["suspeito"]]
    f = aplicar_filtros(base)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total de imoveis", len(f))
    c2.metric("Valor medio",  f"R$ {f['valor'].mean():,.0f}" if len(f) else "—")
    c3.metric("Menor valor",  f"R$ {f['valor'].min():,.0f}"  if len(f) else "—")
    c4.metric("Maior valor",  f"R$ {f['valor'].max():,.0f}"  if len(f) else "—")

    st.divider()
    st.subheader(f"Imoveis encontrados ({len(f)})")

    colunas = [c for c in COLUNAS if c in f.columns]
    st.dataframe(
        f[colunas], use_container_width=True, hide_index=True,
        column_config=COL_CONFIG,
    )

    st.download_button(
        "⬇️ Baixar CSV",
        data=f[colunas].to_csv(index=False).encode("utf-8"),
        file_name="imoveis_filtrado.csv",
        mime="text/csv",
    )

with tab_erros:
    st.markdown(
        "Imoveis cujo valor caiu **fora da faixa plausivel** para o tipo/categoria. "
        "Causas comuns: scraper pegou condominio/IPTU/preco de imovel relacionado, "
        "ou cadastro incompleto na imobiliaria. **Reveja, apague ou re-colete.**"
    )

    erros = aplicar_filtros(df[df["suspeito"]])

    # Anexa info de qual faixa o registro estourou
    if len(erros):
        faixa_info = erros.apply(
            lambda r: "{:,} – {:,}".format(*_faixa(r.get("modalidade",""), r.get("tipo",""))),
            axis=1,
        )
        erros = erros.assign(faixa_esperada=faixa_info)

    cols_erros = ["modalidade", "tipo", "bairro", "valor", "faixa_esperada", "data_coleta", "url"]
    cols_erros = [c for c in cols_erros if c in erros.columns]

    st.dataframe(
        erros[cols_erros], use_container_width=True, hide_index=True,
        column_config={
            **COL_CONFIG,
            "faixa_esperada": "Faixa esperada (R$)",
        },
    )

    if len(erros):
        st.download_button(
            "⬇️ Baixar CSV dos erros",
            data=erros[cols_erros].to_csv(index=False).encode("utf-8"),
            file_name="imoveis_suspeitos.csv",
            mime="text/csv",
        )

        # Mostra as faixas atualmente configuradas — facil de ajustar se algum
        # tipo legitimo (ex: galpao caro) estiver caindo aqui por engano
        with st.expander("ℹ️ Faixas usadas para classificar como suspeito"):
            faixas_df = pd.DataFrame([
                {"modalidade": mod, "tipo": tipo, "min (R$)": v[0], "max (R$)": v[1]}
                for mod, tipos_dict in FAIXAS_VALOR.items()
                for tipo, v in tipos_dict.items()
            ])
            st.dataframe(faixas_df, use_container_width=True, hide_index=True)
            st.caption(
                "Para ajustar, edite o dicionario `FAIXAS_VALOR` no topo de "
                "`dashboard.py` e tambem em `Trabalho_WebScraping.py`."
            )
