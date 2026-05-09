import pandas as pd
import streamlit as st
from pathlib import Path
import plotly.graph_objects as go

# =========================
# Config
# =========================
st.set_page_config(page_title="Dashboard Ventes", layout="wide")

ROOT = Path(__file__).resolve().parent
DATA_PATH = ROOT / "data_analytics" / "sales_all_normalized.csv"

TAX_CA_PCT = 0.123

# =========================
# Helpers
# =========================
def last_november_start(max_dt: pd.Timestamp) -> pd.Timestamp:
    if pd.isna(max_dt):
        return pd.Timestamp("2000-11-01")
    year = max_dt.year if max_dt.month >= 11 else max_dt.year - 1
    return pd.Timestamp(year=year, month=11, day=1)

def canon_artwork_name(s: str) -> str:
    """
    Normalise noms de dessins (artwork_name).
    - Fusion Deadly Poison Sting
    - Remplace tout ce qui contient 'full pack' par 'FULL PACK'
    """
    if not isinstance(s, str):
        return ""
    x = " ".join(s.strip().split())
    low = x.lower()

    # FULL PACK (ton cas : "🌟 FULL PACK 🌟 / Inclut ...")
    if "full pack" in low:
        return "FULL PACK"

    # Deadly Poison Sting
    if ("deadly" in low) and ("poison" in low) and ("sting" in low):
        return "DEADLY POISON STING"

    return x

def canon_option_label(s: str) -> str:
    """
    Normalise les labels d'option (raw_option_name/pack_label).
    """
    if not isinstance(s, str):
        return ""
    x = " ".join(s.strip().split())
    if "full pack" in x.lower():
        return "FULL PACK"
    return x

def safe_num(df: pd.DataFrame, col: str, default=0.0) -> pd.Series:
    if col not in df.columns:
        return pd.Series([default] * len(df), index=df.index, dtype="float64")
    return pd.to_numeric(df[col], errors="coerce").fillna(default)

def pct(a: float, b: float) -> float:
    return (a / b) if b else 0.0

def format_eur(x: float) -> str:
    return f"{x:,.2f} €"

def add_total_labels_vertical(fig: go.Figure, x_vals, totals, yshift=8):
    for x, t in zip(x_vals, totals):
        fig.add_annotation(
            x=x,
            y=t,
            text=f"{t:,.2f} €",
            showarrow=False,
            yshift=yshift
        )

def add_total_labels_horizontal(fig: go.Figure, y_vals, totals, xshift=6):
    for y, t in zip(y_vals, totals):
        fig.add_annotation(
            y=y,
            x=t,
            text=f"{t:,.2f} €",
            showarrow=False,
            xshift=xshift
        )

# =========================
# CSS (bigger KPIs)
# =========================
st.markdown(
    """
    <style>
    div[data-testid="stMetricValue"] {
        font-size: 34px;
        line-height: 1.1;
    }
    div[data-testid="stMetricLabel"] {
        font-size: 16px;
    }
    </style>
    """,
    unsafe_allow_html=True
)

# =========================
# Load
# =========================
@st.cache_data
def load_data(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, encoding="utf-8-sig")
    df["sale_datetime"] = pd.to_datetime(df.get("sale_datetime"), errors="coerce")

    # product_type
    if "product_type" not in df.columns:
        df["product_type"] = "unknown"
    df["product_type"] = df["product_type"].astype(str)

    # artwork_name
    if "artwork_name" not in df.columns:
        if "raw_product_name" in df.columns:
            df["artwork_name"] = df["raw_product_name"].astype(str)
        else:
            df["artwork_name"] = ""

    # ✅ normalise artwork_name (FULL PACK + DPS)
    df["artwork_name"] = df["artwork_name"].astype(str).map(canon_artwork_name)

    # option labels
    if "raw_option_name" in df.columns:
        df["raw_option_name"] = df["raw_option_name"].astype(str).map(canon_option_label)
    if "pack_label" in df.columns:
        df["pack_label"] = df["pack_label"].astype(str).map(canon_option_label)

    # revenue : priorité revenue, sinon revenue_allocated, sinon line_total
    if "revenue" not in df.columns:
        if "revenue_allocated" in df.columns:
            df["revenue"] = safe_num(df, "revenue_allocated", 0.0)
        elif "line_total" in df.columns:
            df["revenue"] = safe_num(df, "line_total", 0.0)
        else:
            df["revenue"] = 0.0
    else:
        df["revenue"] = safe_num(df, "revenue", 0.0)

    # net_profit
    if "net_profit" not in df.columns:
        df["tax_ca"] = safe_num(df, "tax_ca", 0.0)
        df["net_profit"] = df["revenue"] - df["tax_ca"]
    else:
        df["net_profit"] = safe_num(df, "net_profit", 0.0)

    # tax_ca
    if "tax_ca" not in df.columns:
        df["tax_ca"] = df["revenue"] * TAX_CA_PCT
    else:
        df["tax_ca"] = safe_num(df, "tax_ca", 0.0)

    # quantity
    df["quantity"] = safe_num(df, "quantity", 0.0)

    # derived
    df["day"] = df["sale_datetime"].dt.date
    df["month_label"] = df["sale_datetime"].dt.to_period("M").astype(str)  # "YYYY-MM"

    # margin
    df["net_margin"] = df["net_profit"] / df["revenue"].replace({0: pd.NA})

    # round
    df["revenue"] = pd.to_numeric(df["revenue"], errors="coerce").round(2)
    df["net_profit"] = pd.to_numeric(df["net_profit"], errors="coerce").round(2)
    df["tax_ca"] = pd.to_numeric(df["tax_ca"], errors="coerce").round(2)
    df["net_margin"] = pd.to_numeric(df["net_margin"], errors="coerce").round(4)
    df["quantity"] = pd.to_numeric(df["quantity"], errors="coerce").fillna(0).round(0)

    return df

# =========================
# App
# =========================
st.title("📊 Dashboard ventes — Posters & Fonds d’écran")

if not DATA_PATH.exists():
    st.error(f"Fichier introuvable : {DATA_PATH}")
    st.stop()

df = load_data(DATA_PATH)

# =========================
# Global rules
# =========================
max_dt = df["sale_datetime"].max()
start_dt = last_november_start(max_dt)

df = df[df["sale_datetime"] >= start_dt].copy()
df = df[~((df["product_type"] == "wallpaper") & (df["revenue"] <= 0))].copy()

# =========================
# Sidebar filters
# =========================
st.sidebar.header("Filtres")

min_dt = df["sale_datetime"].min()
max_dt = df["sale_datetime"].max()

date_range = st.sidebar.date_input(
    "Période",
    value=(min_dt.date(), max_dt.date()),
    min_value=min_dt.date(),
    max_value=max_dt.date(),
)

types = sorted(df["product_type"].dropna().unique().tolist())
type_sel = st.sidebar.multiselect("Type", types, default=types)
search_art = st.sidebar.text_input("Recherche dessin (contient)", value="")

d0, d1 = date_range
mask = (df["sale_datetime"].dt.date >= d0) & (df["sale_datetime"].dt.date <= d1)
if type_sel:
    mask &= df["product_type"].isin(type_sel)

df_f = df.loc[mask].copy()
if search_art.strip():
    df_f = df_f[df_f["artwork_name"].str.contains(search_art.strip(), case=False, na=False)]

poster = df_f[df_f["product_type"] == "poster"]
wall = df_f[df_f["product_type"] == "wallpaper"]

# =========================
# KPIs
# =========================
st.markdown("## 📌 Indicateurs clés")

rev_total = df_f["revenue"].sum()
profit_total = df_f["net_profit"].sum()
margin_avg = pct(profit_total, rev_total)

profit_poster = poster["net_profit"].sum()
profit_wall = wall["net_profit"].sum()

qty_poster = int(poster["quantity"].sum())
qty_wall = int(wall["quantity"].sum())

k1, k2, k3 = st.columns(3)
k4, k5, k6 = st.columns(3)

with k1:
    st.metric("💰 Revenu total", format_eur(rev_total))
with k2:
    st.metric("📈 Bénéfice total", format_eur(profit_total))
with k3:
    st.metric("📊 Marge moyenne", f"{margin_avg*100:,.1f} %")

with k4:
    st.metric("🖼️ Bénéfice posters", format_eur(profit_poster))
with k5:
    st.metric("📱 Bénéfice fonds d’écran", format_eur(profit_wall))
with k6:
    st.metric("📦 Quantités vendues", f"{qty_poster} posters | {qty_wall} wallpapers")

st.divider()

# =========================
# Monthly profit evolution (ONLY ONCE)
# =========================
st.markdown("## 📆 Évolution du bénéfice par mois")

m = (
    df_f.dropna(subset=["sale_datetime"])
    .groupby(["month_label", "product_type"], as_index=False)
    .agg(profit=("net_profit", "sum"))
)

m_piv = m.pivot(index="month_label", columns="product_type", values="profit").fillna(0.0)
if "poster" not in m_piv.columns:
    m_piv["poster"] = 0.0
if "wallpaper" not in m_piv.columns:
    m_piv["wallpaper"] = 0.0

m_piv["total"] = (m_piv["poster"] + m_piv["wallpaper"]).round(2)
m_piv["poster"] = m_piv["poster"].round(2)
m_piv["wallpaper"] = m_piv["wallpaper"].round(2)

m_piv_chart = m_piv.sort_index(ascending=True).copy()
x_months = m_piv_chart.index.astype(str).tolist()

fig_m = go.Figure()
fig_m.add_bar(
    x=x_months,
    y=m_piv_chart["poster"],
    name="Posters",
    hovertemplate="Mois=%{x}<br>Posters=%{y:.2f}€<extra></extra>",
)
fig_m.add_bar(
    x=x_months,
    y=m_piv_chart["wallpaper"],
    name="Fonds d’écran",
    hovertemplate="Mois=%{x}<br>Wallpapers=%{y:.2f}€<extra></extra>",
)

fig_m.update_layout(
    barmode="stack",
    height=420,
    margin=dict(l=20, r=20, t=40, b=20),
    title="Bénéfice mensuel (total + part posters/fonds d’écran)",
    yaxis_title="Bénéfice (€)",
    xaxis_title="",
    xaxis=dict(
        type="category",
        categoryorder="array",
        categoryarray=x_months,
    ),
)

add_total_labels_vertical(fig_m, x_months, m_piv_chart["total"])

m_tbl = m_piv.reset_index().rename(columns={"month_label": "mois"})
m_tbl["part_posters_%"] = (m_tbl["poster"] / m_tbl["total"].replace({0: pd.NA}) * 100).round(1)
m_tbl["part_wallpapers_%"] = (m_tbl["wallpaper"] / m_tbl["total"].replace({0: pd.NA}) * 100).round(1)
m_tbl = m_tbl[["mois", "total", "poster", "wallpaper", "part_posters_%", "part_wallpapers_%"]]
m_tbl = m_tbl.sort_values("mois", ascending=False).reset_index(drop=True)

col_m_chart, col_m_table = st.columns([1, 1])
with col_m_chart:
    st.plotly_chart(fig_m, width="stretch")
with col_m_table:
    st.dataframe(m_tbl, width="stretch", hide_index=True)

st.divider()

# =========================
# Top 15 artworks by profit
# =========================
st.markdown("## 🎨 Top dessins — par bénéfice")

g = (
    df_f.groupby(["artwork_name", "product_type"], as_index=False)
    .agg(profit=("net_profit", "sum"))
)

g_piv = g.pivot(index="artwork_name", columns="product_type", values="profit").fillna(0.0)
if "poster" not in g_piv.columns:
    g_piv["poster"] = 0.0
if "wallpaper" not in g_piv.columns:
    g_piv["wallpaper"] = 0.0

g_piv["total"] = (g_piv["poster"] + g_piv["wallpaper"]).round(2)
g_piv["poster"] = g_piv["poster"].round(2)
g_piv["wallpaper"] = g_piv["wallpaper"].round(2)

top15 = g_piv.sort_values("total", ascending=False).head(15)

fig_top = go.Figure()
fig_top.add_bar(
    y=top15.index,
    x=top15["poster"],
    name="Posters",
    orientation="h",
    hovertemplate="Dessin=%{y}<br>Posters=%{x:.2f}€<extra></extra>"
)
fig_top.add_bar(
    y=top15.index,
    x=top15["wallpaper"],
    name="Fonds d’écran",
    orientation="h",
    hovertemplate="Dessin=%{y}<br>Wallpapers=%{x:.2f}€<extra></extra>"
)

fig_top.update_layout(
    barmode="stack",
    height=520,
    margin=dict(l=20, r=20, t=40, b=20),
    title="Top 15 dessins par bénéfice (barres empilées posters + fonds d’écran)",
    xaxis_title="Bénéfice (€)",
    yaxis_title="",
)

add_total_labels_horizontal(fig_top, top15.index, top15["total"])

top_tbl = g_piv.reset_index().rename(columns={"artwork_name": "dessin"})
top_tbl["part_posters_%"] = (top_tbl["poster"] / top_tbl["total"].replace({0: pd.NA}) * 100).round(1)
top_tbl["part_wallpapers_%"] = (top_tbl["wallpaper"] / top_tbl["total"].replace({0: pd.NA}) * 100).round(1)
top_tbl = top_tbl[["dessin", "total", "poster", "wallpaper", "part_posters_%", "part_wallpapers_%"]]
top_tbl = top_tbl.sort_values("total", ascending=False).reset_index(drop=True)

col_t_chart, col_t_table = st.columns([1, 1])
with col_t_chart:
    st.plotly_chart(fig_top, width="stretch")
with col_t_table:
    st.dataframe(top_tbl, width="stretch", hide_index=True)

st.divider()

# =========================
# Drilldown per artwork
# =========================
st.markdown("## 🔎 Détail par dessin")

choices = top_tbl["dessin"].tolist()[:500] if len(top_tbl) else sorted(df_f["artwork_name"].unique().tolist())
selected = st.selectbox("Choisir un dessin", choices)

if selected:
    dsel = df_f[df_f["artwork_name"] == selected].copy()
    psel = dsel[dsel["product_type"] == "poster"].copy()
    wsel = dsel[dsel["product_type"] == "wallpaper"].copy()

    prof_total = round(dsel["net_profit"].sum(), 2)
    prof_p = round(psel["net_profit"].sum(), 2)
    prof_w = round(wsel["net_profit"].sum(), 2)

    share_p = pct(prof_p, prof_total)
    share_w = pct(prof_w, prof_total)

    qty_p = int(psel["quantity"].sum())
    qty_w = int(wsel["quantity"].sum())

    a1, a2, a3, a4 = st.columns(4)
    a1.metric("Bénéfice total", format_eur(prof_total))
    a2.metric("Posters", f"{format_eur(prof_p)}  ({share_p*100:,.1f}%)")
    a3.metric("Wallpapers", f"{format_eur(prof_w)}  ({share_w*100:,.1f}%)")
    a4.metric("Quantités", f"{qty_p} posters | {qty_w} wallpapers")

    ql, qr = st.columns([1, 1])

    with ql:
        st.markdown("### Quantités vendues")
        by_type_qty = dsel.groupby("product_type", as_index=False).agg(qty=("quantity", "sum"))
        by_type_qty["qty"] = by_type_qty["qty"].round(0).astype(int)
        by_type_qty = by_type_qty.sort_values("qty", ascending=False)
        st.dataframe(by_type_qty, width="stretch", hide_index=True)

    with qr:
        st.markdown("### Posters : par taille")
        if "size" in psel.columns and len(psel):
            by_size = psel.groupby("size", as_index=False).agg(qty=("quantity", "sum"))
            by_size["qty"] = by_size["qty"].round(0).astype(int)
            by_size = by_size.sort_values("qty", ascending=False)
            st.dataframe(by_size, width="stretch", hide_index=True)
        else:
            st.info("Aucun poster pour ce dessin ou colonne 'size' manquante.")

    st.markdown("### Lignes brutes (récentes en haut)")
    cols_show = [c for c in [
        "sale_datetime", "product_type", "quantity", "revenue", "net_profit",
        "order_id", "size", "raw_option_name", "pack_label", "wallpaper_kind"
    ] if c in dsel.columns]

    raw = dsel[cols_show].sort_values("sale_datetime", ascending=False).copy()
    for c in ["revenue", "net_profit"]:
        if c in raw.columns:
            raw[c] = pd.to_numeric(raw[c], errors="coerce").round(2)

    st.dataframe(raw, width="stretch", hide_index=True)

st.divider()

# =========================
# Daily profit evolution (BOTTOM) stacked bars + table
# =========================
st.markdown("## 📅 Évolution du bénéfice par jour")

d = (
    df_f.dropna(subset=["sale_datetime"])
    .groupby(["day", "product_type"], as_index=False)
    .agg(profit=("net_profit", "sum"))
)

d_piv = d.pivot(index="day", columns="product_type", values="profit").fillna(0.0)
if "poster" not in d_piv.columns:
    d_piv["poster"] = 0.0
if "wallpaper" not in d_piv.columns:
    d_piv["wallpaper"] = 0.0

d_piv["total"] = (d_piv["poster"] + d_piv["wallpaper"]).round(2)
d_piv["poster"] = d_piv["poster"].round(2)
d_piv["wallpaper"] = d_piv["wallpaper"].round(2)

fig_d = go.Figure()
fig_d.add_bar(
    x=d_piv.index.astype(str),
    y=d_piv["poster"],
    name="Posters",
    hovertemplate="Jour=%{x}<br>Posters=%{y:.2f}€<extra></extra>"
)
fig_d.add_bar(
    x=d_piv.index.astype(str),
    y=d_piv["wallpaper"],
    name="Fonds d’écran",
    hovertemplate="Jour=%{x}<br>Wallpapers=%{y:.2f}€<extra></extra>"
)

fig_d.update_layout(
    barmode="stack",
    height=420,
    margin=dict(l=20, r=20, t=40, b=40),
    title="Bénéfice journalier (total + part posters/fonds d’écran)",
    yaxis_title="Bénéfice (€)",
    xaxis_title="",
    xaxis=dict(type="category"),
)

# pas de labels totaux sur le chart jour (comme demandé)

d_tbl = d_piv.reset_index().rename(columns={"day": "jour"})
d_tbl["part_posters_%"] = (d_tbl["poster"] / d_tbl["total"].replace({0: pd.NA}) * 100).round(1)
d_tbl["part_wallpapers_%"] = (d_tbl["wallpaper"] / d_tbl["total"].replace({0: pd.NA}) * 100).round(1)
d_tbl = d_tbl[["jour", "total", "poster", "wallpaper", "part_posters_%", "part_wallpapers_%"]]
d_tbl = d_tbl.sort_values("jour", ascending=False).reset_index(drop=True)

col_d_chart, col_d_table = st.columns([1, 1])
with col_d_chart:
    st.plotly_chart(fig_d, width="stretch")
with col_d_table:
    st.dataframe(d_tbl, width="stretch", hide_index=True)
