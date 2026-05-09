import pandas as pd
from pathlib import Path

# =========================
# Paths
# =========================
ROOT = Path(__file__).resolve().parent
CSV_PATH = ROOT / "data_raw" / "Extras_purchase_list.csv"
OUT_DIR = ROOT / "data_transformed"
OUT_DIR.mkdir(parents=True, exist_ok=True)

OUT_PATH = OUT_DIR / "sale_lines_clean_wallpapers.csv"

TAX_CA_PCT = 0.133

FREEBIE_EXTRAS = {
    "WONDERLAND - Laskunk / Fond d'écran",
    "2EN1 - 2T / Fond d'écran",
    "OVERLOOK 237 - Laskunk / Fond d'écran",
    "PESADAO - Flyer Soirée / Fond d'écran",
    "RAVEN TAIL - Traffy / Fond d'écran",
}


print("📂 Loading:", CSV_PATH)

# =========================
# Load CSV (robuste)
# =========================
try:
    df_raw = pd.read_csv(CSV_PATH, encoding="utf-8-sig")
except UnicodeDecodeError:
    df_raw = pd.read_csv(CSV_PATH, encoding="cp1252")

# Fix mojibake (NÃ©pal -> Népal, tÃ©lÃ©phone -> téléphone)
def fix_mojibake(series: pd.Series) -> pd.Series:
    mask = series.astype(str).str.contains("Ã|Â|â€™", na=False)
    out = series.copy()
    out.loc[mask] = (
        out.loc[mask]
        .astype(str)
        .str.encode("latin1", errors="ignore")
        .str.decode("utf-8", errors="ignore")
    )
    return out

for col in ["Extras Name", "Supporter Name"]:
    if col in df_raw.columns:
        df_raw[col] = fix_mojibake(df_raw[col])

# =========================
# Normalize headers
# =========================
rename = {
    "Supporter Name": "supporter_name",
    "Supporter Email": "supporter_email",
    "Extras Name": "extras_name",
    "Quantity": "quantity",
    "Total Amount": "total_amount",
    "Currency": "currency",
    "Purchased On": "purchased_on",
}
df = df_raw.rename(columns=rename).copy()

# Plateforme
df["platform"] = "bmac"

# Flag freebies (après fix_mojibake, donc texte lisible)
df["is_freebie"] = df["extras_name"].astype(str).str.strip().isin(FREEBIE_EXTRAS)

# Option A (recommandée): on les enlève complètement du dataset
df = df[~df["is_freebie"]].copy()


# Datetime
df["sale_datetime"] = pd.to_datetime(df["purchased_on"], errors="coerce")

# Numerics
df["quantity"] = pd.to_numeric(df["quantity"], errors="coerce").fillna(1).astype(int)
df["total_amount"] = pd.to_numeric(df["total_amount"], errors="coerce").fillna(0.0)

# Prix unitaire
df["unit_price"] = df["total_amount"] / df["quantity"].replace({0: pd.NA})

# =========================
# Parse "extras_name"
# Exemple: "444 NUITS - Népal / Pack de fonds d'écran PC + téléphone"
# =========================
def extract_artwork_name(extras: str) -> str:
    if not isinstance(extras, str) or not extras.strip():
        return None
    # On prend la partie avant " - " comme nom du dessin (ex: "444 NUITS")
    return extras.split(" - ", 1)[0].strip()

def extract_pack_label(extras: str) -> str:
    if not isinstance(extras, str) or not extras.strip():
        return None
    # On garde ce qui suit " - " si présent, sinon tout
    if " - " in extras:
        return extras.split(" - ", 1)[1].strip()
    return extras.strip()

def infer_wallpaper_kind(pack_label: str) -> str:
    if not isinstance(pack_label, str) or not pack_label.strip():
        return None
    s = pack_label.lower()

    has_pc = ("pc" in s) or ("ordinateur" in s) or ("desktop" in s)
    has_phone = ("téléphone" in s) or ("telephone" in s) or ("mobile" in s) or ("phone" in s)

    if has_pc and has_phone:
        return "pack_pc_phone"
    if has_pc:
        return "pc"
    if has_phone:
        return "phone"
    return "unknown"

df["raw_product_name"] = df["extras_name"].apply(extract_artwork_name)
df["pack_label"] = df["extras_name"].apply(extract_pack_label)
df["wallpaper_kind"] = df["pack_label"].apply(infer_wallpaper_kind)

# Type produit
df["product_type"] = "wallpaper"

# Customer id (email prioritaire, sinon pseudo)
df["customer_id"] = df["supporter_email"].astype(str).where(df["supporter_email"].notna(), None)
df.loc[df["customer_id"].isna() & df["supporter_name"].notna(), "customer_id"] = "bmac:" + df["supporter_name"].astype(str)

# ID ligne (stable)
df["sale_line_id"] = (
    "bmac-"
    + df.index.astype(str)
)

# =========================
# Output "sale lines" clean
# =========================
out_cols = [
    "sale_line_id",
    "platform",
    "sale_datetime",
    "customer_id",
    "supporter_name",
    "supporter_email",
    "extras_name",
    "raw_product_name",
    "pack_label",
    "wallpaper_kind",
    "product_type",
    "quantity",
    "unit_price",
    "total_amount",
    "currency",
]

out = df[out_cols].copy()

# Renommer champs pour rester cohérent avec posters
out = out.rename(columns={
    "extras_name": "raw_option_name",   # on réutilise ce champ comme "option/variant"
    "total_amount": "line_total"
})

out["tax_ca"] = out["line_total"] * TAX_CA_PCT
out["net_profit"] = out["line_total"] - out["tax_ca"]
out["net_margin"] = out["net_profit"] / out["line_total"].replace({0: pd.NA})


out.to_csv(OUT_PATH, index=False, encoding="utf-8-sig")

print("\n✅ Export terminé :", OUT_PATH)
print("📊 Lignes :", len(out))
print(out[["raw_product_name", "wallpaper_kind", "quantity", "line_total"]].head(10).to_string(index=False))
