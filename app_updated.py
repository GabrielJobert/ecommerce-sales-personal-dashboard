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

# Fichiers manuels (coûts / revenus hors ventes)
COUTS_ISO_PATHS = [ROOT / "data_raw" / "couts_isoles.csv", ROOT / "couts_isoles.csv"]
REV_ISO_PATHS = [ROOT / "data_raw" / "revenu_isoles.csv", ROOT / "revenu_isoles.csv"]

# Taxes demandées
URSSAF_PCT = 0.123
IMPOT_PCT = 0.010
TAX_TOTAL_PCT = URSSAF_PCT + IMPOT_PCT  # 13.3%

# =========================
# Helpers
# =========================
def last_november_start(max_dt: pd.Timestamp) -> pd.Timestamp:
    if pd.isna(max_dt):
        return pd.Timestamp("2000-11-01")
    year = max_dt.year if max_dt.month >= 11 else max_dt.year - 1
    return pd.Timestamp(year=year, month=11, day=1)

def canon_artwork_name(s: str) -> str:
    if not isinstance(s, str):
        return ""
    x = " ".join(s.strip().split())
    low = x.lower()
    if "full pack" in low:
        return "FULL PACK"
    if ("deadly" in low) and ("poison" in low) and ("sting" in low):
        return "DEADLY POISON STING"
    return x

def canon_option_label(s: str) -> str:
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
        fig.add_annotation(x=x, y=t, text=f"{t:,.2f} €", showarrow=False, yshift=yshift)

def add_total_labels_horizontal(fig: go.Figure, y_vals, totals, xshift=6):
    for y, t in zip(y_vals, totals):
        fig.add_annotation(y=y, x=t, text=f"{t:,.2f} €", showarrow=False, xshift=xshift)

def read_semicolon_csv_robust(path: Path) -> pd.DataFrame:
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin1"):
        try:
            return pd.read_csv(path, encoding=enc, sep=";")
        except Exception:
            pass
    return pd.read_csv(path)

def load_isolated_costs() -> pd.DataFrame:
    p = next((p for p in COUTS_ISO_PATHS if p.exists()), None)
    if not p:
        return pd.DataFrame(columns=["name", "amount", "date", "sub_category", "month_label"])
    dfc = read_semicolon_csv_robust(p).copy()
    dfc = dfc.rename(columns={
        "Name": "name",
        "Montant": "amount",
        "Date": "date",
        "Sous-Catégorie": "sub_category",
        "Sous-catégorie": "sub_category",
    })
    dfc["date"] = pd.to_datetime(dfc.get("date"), dayfirst=True, errors="coerce")
    dfc["month_label"] = dfc["date"].dt.to_period("M").astype(str)
    dfc["amount"] = pd.to_numeric(dfc.get("amount"), errors="coerce").fillna(0.0)
    dfc["sub_category"] = dfc.get("sub_category", "Autre").astype(str).fillna("Autre")
    return dfc

def load_isolated_revenues() -> pd.DataFrame:
    p = next((p for p in REV_ISO_PATHS if p.exists()), None)
    if not p:
        return pd.DataFrame(columns=["name", "amount", "date", "category", "sub_category", "month_label"])
    dfr = read_semicolon_csv_robust(p).copy()
    dfr = dfr.rename(columns={
        "Name": "name",
        "Montant": "amount",
        "Date": "date",
        "Catégorie": "category",
        "Sous-catégorie": "sub_category",
        "Sous-Catégorie": "sub_category",
    })
    dfr["date"] = pd.to_datetime(dfr.get("date"), dayfirst=True, errors="coerce")
    dfr["month_label"] = dfr["date"].dt.to_period("M").astype(str)
    dfr["amount"] = pd.to_numeric(dfr.get("amount"), errors="coerce").fillna(0.0)
    dfr["category"] = dfr.get("category", "Autre").astype(str).fillna("Autre")
    dfr["sub_category"] = dfr.get("sub_category", "").astype(str).fillna("")
    return dfr

# =========================
# CSS (bigger KPIs)
# =========================
st.markdown(
    """
    <style>
    div[data-testid="stMetricValue"] { font-size: 34px; line-height: 1.1; }
    div[data-testid="stMetricLabel"] { font-size: 16px; }
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

    if "product_type" not in df.columns:
        df["product_type"] = "unknown"
    df["product_type"] = df["product_type"].astype(str)

    if "artwork_name" not in df.columns:
        if "raw_product_name" in df.columns:
            df["artwork_name"] = df["raw_product_name"].astype(str)
        else:
            df["artwork_name"] = ""
    df["artwork_name"] = df["artwork_name"].astype(str).map(canon_artwork_name)

    if "raw_option_name" in df.columns:
        df["raw_option_name"] = df["raw_option_name"].astype(str).map(canon_option_label)
    if "pack_label" in df.columns:
        df["pack_label"] = df["pack_label"].astype(str).map(canon_option_label)

    if "revenue" not in df.columns:
        if "revenue_allocated" in df.columns:
            df["revenue"] = safe_num(df, "revenue_allocated", 0.0)
        elif "line_total" in df.columns:
            df["revenue"] = safe_num(df, "line_total", 0.0)
        else:
            df["revenue"] = 0.0
    else:
        df["revenue"] = safe_num(df, "revenue", 0.0)

    if "net_profit" not in df.columns:
        df["net_profit"] = df["revenue"]
    else:
        df["net_profit"] = safe_num(df, "net_profit", 0.0)

    df["quantity"] = safe_num(df, "quantity", 0.0)

    df["day"] = df["sale_datetime"].dt.date
    df["month_label"] = df["sale_datetime"].dt.to_period("M").astype(str)

    df["revenue"] = pd.to_numeric(df["revenue"], errors="coerce").fillna(0.0).round(2)
    df["net_profit"] = pd.to_numeric(df["net_profit"], errors="coerce").fillna(0.0).round(2)
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

max_dt = df["sale_datetime"].max()
start_dt = last_november_start(max_dt)

df = df[df["sale_datetime"] >= start_dt].copy()
df = df[~((df["product_type"] == "wallpaper") & (df["revenue"] <= 0))].copy()

# =========================
# Sidebar filters
# =========================
st.sidebar.header("Filtres")

# =========================
# Excel (revenus/couts isolés) — chargés tôt pour inclure leurs dates dans le sélecteur
# =========================
df_costs_iso = load_isolated_costs()
df_revs_iso = load_isolated_revenues()

min_dt = df["sale_datetime"].min()
max_dt = df["sale_datetime"].max()

# étend la plage aux excels (si présents)
iso_min = pd.to_datetime(pd.concat([
    df_costs_iso["date"] if len(df_costs_iso) else pd.Series(dtype="datetime64[ns]"),
    df_revs_iso["date"] if len(df_revs_iso) else pd.Series(dtype="datetime64[ns]"),
], ignore_index=True), errors="coerce").min()
iso_max = pd.to_datetime(pd.concat([
    df_costs_iso["date"] if len(df_costs_iso) else pd.Series(dtype="datetime64[ns]"),
    df_revs_iso["date"] if len(df_revs_iso) else pd.Series(dtype="datetime64[ns]"),
], ignore_index=True), errors="coerce").max()

if pd.notna(iso_min):
    min_dt = min(min_dt, iso_min)
if pd.notna(iso_max):
    max_dt = max(max_dt, iso_max)

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
# Excel (revenus/couts isolés)
# =========================
df_costs_iso_f = df_costs_iso[(df_costs_iso["date"].dt.date >= d0) & (df_costs_iso["date"].dt.date <= d1)].copy()
df_revs_iso_f  = df_revs_iso[(df_revs_iso["date"].dt.date >= d0) & (df_revs_iso["date"].dt.date <= d1)].copy()

depenses_indiv_total = df_costs_iso_f["amount"].sum() if len(df_costs_iso_f) else 0.0
revenus_excel_total = df_revs_iso_f["amount"].sum() if len(df_revs_iso_f) else 0.0

poster_excel_profit = df_revs_iso_f[df_revs_iso_f["category"].str.lower().eq("poster")]["amount"].sum() if len(df_revs_iso_f) else 0.0

commissions_excel = df_revs_iso_f[df_revs_iso_f["category"].str.lower().eq("commissions")].copy() if len(df_revs_iso_f) else pd.DataFrame(columns=df_revs_iso_f.columns)
commissions_total = commissions_excel["amount"].sum() if len(commissions_excel) else 0.0

cover_excel_profit = 0.0
if len(commissions_excel):
    cover_excel_profit = commissions_excel[
        commissions_excel["sub_category"].astype(str).str.contains("cover", case=False, na=False)
    ]["amount"].sum()

# =========================
# KPIs
# =========================
st.markdown("## 📌 Indicateurs clés")

rev_sales_total = df_f["revenue"].sum()
profit_sales_total = df_f["net_profit"].sum()

rev_total = rev_sales_total + revenus_excel_total
profit_total = profit_sales_total + revenus_excel_total  # tout est net -> revenu excel = bénéfice
profit_after_fixed = profit_total - depenses_indiv_total
margin_avg = pct(profit_after_fixed, rev_total)

profit_poster = poster["net_profit"].sum() + poster_excel_profit
profit_wall = wall["net_profit"].sum()

qty_poster = int(poster["quantity"].sum())
qty_wall = int(wall["quantity"].sum())

k1, k2, k3, k4 = st.columns(4)
k5, k6, k7, k8 = st.columns(4)

with k1:
    st.metric("💰 Revenu total", format_eur(rev_total))
with k2:
    st.metric("📈 Bénéfice total", format_eur(profit_total))
with k3:
    st.metric("📊 Marge moyenne", f"{margin_avg*100:,.1f} %")
with k4:
    st.metric("🧾 Bénéfice commission", format_eur(commissions_total))

with k5:
    st.metric("💸 Dépenses individuelles", format_eur(depenses_indiv_total))
with k6:
    st.metric("🖼️ Bénéfice posters", format_eur(profit_poster))
with k7:
    st.metric("📱 Bénéfice fonds d’écran", format_eur(profit_wall))
with k8:
    st.metric("📦 Quantités vendues", f"{qty_poster} posters | {qty_wall} wallpapers")

st.divider()

# =========================
# Évolution du bénéfice par mois (Posters + Wallpapers + Commission)
# =========================
st.markdown("## 📆 Évolution du bénéfice par mois")

m_sales = (
    df_f.dropna(subset=["sale_datetime"])
    .groupby(["month_label", "product_type"], as_index=False)
    .agg(profit=("net_profit", "sum"))
)

m_piv = m_sales.pivot(index="month_label", columns="product_type", values="profit").fillna(0.0)
if "poster" not in m_piv.columns:
    m_piv["poster"] = 0.0
if "wallpaper" not in m_piv.columns:
    m_piv["wallpaper"] = 0.0

m_excel = (
    df_revs_iso_f.groupby(["month_label", "category"], as_index=False).agg(amount=("amount", "sum"))
    if len(df_revs_iso_f) else pd.DataFrame(columns=["month_label", "category", "amount"])
)

m_excel_poster = m_excel[m_excel["category"].str.lower().eq("poster")].set_index("month_label")["amount"] if len(m_excel) else pd.Series(dtype=float)
m_excel_comm = m_excel[m_excel["category"].str.lower().eq("commissions")].set_index("month_label")["amount"] if len(m_excel) else pd.Series(dtype=float)

m_piv["poster"] = (m_piv["poster"] + m_excel_poster.reindex(m_piv.index).fillna(0.0)).round(2)
m_piv["commission"] = m_excel_comm.reindex(m_piv.index).fillna(0.0).round(2)
m_piv["wallpaper"] = m_piv["wallpaper"].round(2)

m_piv["total"] = (m_piv["poster"] + m_piv["wallpaper"] + m_piv["commission"]).round(2)

m_piv_chart = m_piv.sort_index(ascending=True).copy()
x_months = m_piv_chart.index.astype(str).tolist()

fig_m = go.Figure()
for name, col in [("Posters", "poster"), ("Fonds d’écran", "wallpaper"), ("Commission", "commission")]:
    vals = m_piv_chart[col]
    fig_m.add_bar(
        x=x_months,
        y=vals,
        name=name,
        text=[f"{v:,.0f}€" if v else "" for v in vals],
        textposition="inside",
        hovertemplate="Mois=%{x}<br>" + name + "=%{y:.2f}€<extra></extra>",
    )

fig_m.update_layout(
    barmode="stack",
    height=420,
    margin=dict(l=20, r=20, t=40, b=20),
    title="Bénéfice mensuel (posters + fonds d’écran + commission)",
    yaxis_title="Bénéfice (€)",
    xaxis_title="",
    xaxis=dict(type="category", categoryorder="array", categoryarray=x_months),
)

add_total_labels_vertical(fig_m, x_months, m_piv_chart["total"])

m_tbl = m_piv.reset_index().rename(columns={"month_label": "mois"})
m_tbl = m_tbl[["mois", "total", "poster", "wallpaper", "commission"]].sort_values("mois", ascending=False).reset_index(drop=True)

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
fig_top.add_bar(y=top15.index, x=top15["poster"], name="Posters", orientation="h",
                hovertemplate="Dessin=%{y}<br>Posters=%{x:.2f}€<extra></extra>")
fig_top.add_bar(y=top15.index, x=top15["wallpaper"], name="Fonds d’écran", orientation="h",
                hovertemplate="Dessin=%{y}<br>Wallpapers=%{x:.2f}€<extra></extra>")

fig_top.update_layout(
    barmode="stack",
    height=520,
    margin=dict(l=20, r=20, t=40, b=20),
    title="Top 15 dessins par bénéfice (posters + fonds d’écran)",
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
# Analyse des coûts (sous Top dessins)
# =========================
st.markdown("## 💸 Analyse des coûts")

costs_m = (
    df_costs_iso_f.dropna(subset=["date"])
    .groupby(["month_label", "sub_category"], as_index=False)
    .agg(amount=("amount", "sum"))
) if len(df_costs_iso_f) else pd.DataFrame(columns=["month_label", "sub_category", "amount"])

if len(costs_m):
    pivot_c = costs_m.pivot(index="month_label", columns="sub_category", values="amount").fillna(0.0)
    pivot_c = pivot_c.sort_index(ascending=True)
    x_months_c = pivot_c.index.astype(str).tolist()
    totals_c = pivot_c.sum(axis=1).round(2)

    fig_cost_month = go.Figure()
    # Palette bleue cohérente
    blue_palette = [
        "rgba(116,192,252,0.90)",
        "rgba(77,171,247,0.90)",
        "rgba(51,154,240,0.90)",
        "rgba(34,139,230,0.90)",
        "rgba(28,126,214,0.90)",
        "rgba(25,113,194,0.90)",
        "rgba(24,100,171,0.90)",
    ]
    for i, cat in enumerate(pivot_c.columns):
        vals = pivot_c[cat].round(2)
        fig_cost_month.add_bar(
            x=x_months_c, y=vals, name=str(cat),
            marker_color=blue_palette[i % len(blue_palette)],
            text=[f"{v:,.0f}€" if v else "" for v in vals],
            textposition="inside",
            hovertemplate="Mois=%{x}<br>" + str(cat) + "=%{y:.2f}€<extra></extra>",
        )

    fig_cost_month.update_layout(
        barmode="stack",
        height=420,
        margin=dict(l=20, r=20, t=40, b=20),
        title="Dépenses individuelles par mois (hors coûts posters & hors impôts)",
        yaxis_title="Montant (€)",
        xaxis_title="",
        xaxis=dict(type="category", categoryorder="array", categoryarray=x_months_c),
        legend_title_text="Catégories",
    )
    add_total_labels_vertical(fig_cost_month, x_months_c, totals_c)

    cat_totals = (
        df_costs_iso_f.groupby("sub_category", as_index=False)
        .agg(amount=("amount", "sum"))
        .sort_values("amount", ascending=False)
    )

    fig_cost_pie = go.Figure(
        data=[go.Pie(
            labels=cat_totals["sub_category"],
            values=cat_totals["amount"],
            textinfo="label+value",
            hole=0.35,
            marker=dict(colors=blue_palette[:len(cat_totals)]),
        )]
    )
    total_fixed = float(cat_totals["amount"].sum())

    fig_cost_pie.update_layout(
        height=420,
        margin=dict(l=10, r=10, t=40, b=10),
        title="Dépenses fixes — par catégorie",
    )
    # Affiche le total au centre
    fig_cost_pie.add_annotation(
        x=0.5, y=0.5,
        text=f"Total<br>{total_fixed:,.2f} €",
        showarrow=False,
        font=dict(size=14),
    )

    c_left, c_right = st.columns([3, 1])
    with c_left:
        st.plotly_chart(fig_cost_month, width="stretch")
    with c_right:
        st.plotly_chart(fig_cost_pie, width="stretch")
else:
    st.info("Aucune dépense individuelle sur la période sélectionnée.")

st.divider()

# =========================
# Analyse des taxes
# =========================
st.markdown("## 🧾 Analyse des taxes")

df_sales_tax_base = df_f[df_f["product_type"].isin(["poster", "wallpaper"])].copy()
ca_m = df_sales_tax_base.groupby("month_label", as_index=False).agg(ca=("revenue", "sum"))

if len(ca_m):
    ca_m["urssaf"] = (ca_m["ca"] * URSSAF_PCT).round(2)
    ca_m["impot"] = (ca_m["ca"] * IMPOT_PCT).round(2)
    ca_m = ca_m.sort_values("month_label", ascending=True)
    x_tax = ca_m["month_label"].astype(str).tolist()

    fig_tax = go.Figure()
    fig_tax.add_bar(x=x_tax, y=ca_m["urssaf"], name="URSSAF (12.3%)",
                    marker_color="rgba(77,171,247,0.90)",
                    text=[f"{v:,.0f}€" if v else "" for v in ca_m["urssaf"]],
                    textposition="inside",
                    hovertemplate="Mois=%{x}<br>URSSAF=%{y:.2f}€<extra></extra>")
    fig_tax.add_bar(x=x_tax, y=ca_m["impot"], name="Impôt (1%)",
                    marker_color="rgba(34,139,230,0.90)",
                    text=[f"{v:,.0f}€" if v else "" for v in ca_m["impot"]],
                    textposition="inside",
                    hovertemplate="Mois=%{x}<br>Impôt=%{y:.2f}€<extra></extra>")
    fig_tax.update_layout(
        barmode="stack",
        height=380,
        margin=dict(l=20, r=20, t=40, b=20),
        title="Taxes mensuelles (13.3% du CA posters + fonds d’écran)",
        yaxis_title="Montant (€)",
        xaxis_title="",
        xaxis=dict(type="category", categoryorder="array", categoryarray=x_tax),
    )
    tax_totals = (ca_m["urssaf"] + ca_m["impot"]).round(2)
    add_total_labels_vertical(fig_tax, x_tax, tax_totals)

    rev_m_sales = df_f.groupby("month_label", as_index=False).agg(rev_sales=("revenue", "sum"))

    rev_m_excel = (
        df_revs_iso_f.groupby("month_label", as_index=False).agg(rev_excel=("amount", "sum"))
        if len(df_revs_iso_f)
        else pd.DataFrame(columns=["month_label", "rev_excel"])
    )

    # union de tous les mois présents dans ventes OU excel
    all_months = pd.DataFrame({
        "month_label": sorted(set(rev_m_sales["month_label"]).union(set(rev_m_excel["month_label"])))
    })

    rev_m = (
        all_months
        .merge(rev_m_sales, on="month_label", how="left")
        .merge(rev_m_excel, on="month_label", how="left")
        .fillna(0.0)
    )

    rev_m["rev_with_excel"] = (rev_m["rev_sales"] + rev_m["rev_excel"]).round(2)
    rev_m = rev_m.sort_values("month_label", ascending=True)

    x_rev = rev_m["month_label"].astype(str).tolist()

    fig_rev = go.Figure()

    fig_rev.add_bar(
        x=x_rev,
        y=rev_m["rev_sales"],
        name="Sans Excel",
        text=[f"{v:,.0f}€" if v else "" for v in rev_m["rev_sales"]],
        textposition="outside",
        hovertemplate="Mois=%{x}<br>Sans Excel=%{y:.2f}€<extra></extra>",
    )

    fig_rev.add_bar(
        x=x_rev,
        y=rev_m["rev_with_excel"],
        name="Avec Excel",
        text=[f"{v:,.0f}€" if v else "" for v in rev_m["rev_with_excel"]],
        textposition="outside",
        hovertemplate="Mois=%{x}<br>Avec Excel=%{y:.2f}€<extra></extra>",
    )

    fig_rev.update_layout(
        barmode="group",
        height=420,
        margin=dict(l=20, r=20, t=40, b=20),
        title="Revenu mensuel : sans Excel vs avec Excel",
        yaxis_title="Montant (€)",
        xaxis_title="",
        xaxis=dict(type="category", categoryorder="array", categoryarray=x_rev),
        legend_title_text="Série",
    )

    t1, t2 = st.columns([1, 1])
    with t1:
        st.plotly_chart(fig_tax, width="stretch")
    with t2:
        st.plotly_chart(fig_rev, width="stretch")
else:
    st.info("Aucune vente posters/fonds d’écran sur la période sélectionnée.")

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
# Daily profit evolution (BOTTOM)
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

fig_d = go.Figure()
fig_d.add_bar(x=d_piv.index.astype(str), y=d_piv["poster"], name="Posters",
              hovertemplate="Jour=%{x}<br>Posters=%{y:.2f}€<extra></extra>")
fig_d.add_bar(x=d_piv.index.astype(str), y=d_piv["wallpaper"], name="Fonds d’écran",
              hovertemplate="Jour=%{x}<br>Wallpapers=%{y:.2f}€<extra></extra>")

fig_d.update_layout(
    barmode="stack",
    height=420,
    margin=dict(l=20, r=20, t=40, b=40),
    title="Bénéfice journalier (posters + fonds d’écran)",
    yaxis_title="Bénéfice (€)",
    xaxis_title="",
    xaxis=dict(type="category"),
)

d_tbl = d_piv.reset_index().rename(columns={"day": "jour"})
d_tbl = d_tbl[["jour", "total", "poster", "wallpaper"]].sort_values("jour", ascending=False).reset_index(drop=True)

col_d_chart, col_d_table = st.columns([1, 1])
with col_d_chart:
    st.plotly_chart(fig_d, width="stretch")
with col_d_table:
    st.dataframe(d_tbl, width="stretch", hide_index=True)
