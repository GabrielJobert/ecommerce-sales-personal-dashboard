import pandas as pd
import re
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RAW_DIR = ROOT / "data_raw"
CSV_PATH = RAW_DIR / "orders-all.csv"
OUT_DIR = ROOT / "data_transformed"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# =========================
# Load CSV (robuste)
# =========================

def resolve_orders_csv() -> Path:
    # 1) fichier attendu
    if CSV_PATH.exists():
        return CSV_PATH

    # 2) petite attente si iCloud n'a pas fini
    for _ in range(20):
        if CSV_PATH.exists():
            return CSV_PATH
        time.sleep(0.25)

    # 3) fallback: cherche les variantes
    candidates = sorted(
        RAW_DIR.glob("orders-all*.csv"),
        key=lambda p: p.stat().st_mtime,
        reverse=True
    )
    if candidates:
        print(f"⚠️ orders-all.csv introuvable, fallback sur: {candidates[0].name}")
        return candidates[0]

    raise FileNotFoundError(f"Aucun fichier orders-all*.csv trouvé dans {RAW_DIR}")

CSV_PATH = resolve_orders_csv()
print("📂 Loading:", CSV_PATH)

try:
    df_raw = pd.read_csv(CSV_PATH, encoding="utf-8-sig")
except UnicodeDecodeError:
    df_raw = pd.read_csv(CSV_PATH, encoding="cp1252")

# Fix mojibake (Ã— -> ×) dans Items + Shipping method
def fix_mojibake(series: pd.Series) -> pd.Series:
    mask = series.astype(str).str.contains("Ã|Â|â€™|â‚¬", na=False)
    out = series.copy()
    out.loc[mask] = (
        out.loc[mask]
        .astype(str)
        .str.encode("latin1", errors="ignore")
        .str.decode("utf-8", errors="ignore")
    )
    return out

for col in ["Items", "Shipping methods"]:
    if col in df_raw.columns:
        df_raw[col] = fix_mojibake(df_raw[col])


TAX_CA_PCT = 0.133          # 12.3% du chiffre d'affaires
STRIPE_FEE_PCT = 0.015     # modifiable
STRIPE_FEE_FIXED = 0.25     # modifiable (EUR)


# =========================
# Rename columns
# =========================
rename = {
    "Number": "order_id",
    "Buyer first name": "buyer_first_name",
    "Buyer last name": "buyer_last_name",
    "Buyer email": "buyer_email",
    "Buyer phone number": "buyer_phone",
    "Date": "date",
    "Time": "time",
    "Status": "status",
    "Payment status": "payment_status",
    "Transaction ID": "transaction_id",
    "Shipping status": "shipping_status",
    "Shipping methods": "shipping_method",
    "Shipping address 1": "ship_addr1",
    "Shipping address 2": "ship_addr2",
    "Shipping city": "ship_city",
    "Shipping state": "ship_state",
    "Shipping zip": "ship_zip",
    "Shipping country": "ship_country",
    "Currency": "currency",
    "Items": "items_raw",
    "Item count": "item_count",
    "Item total": "item_total",
    "Total price": "total_price",
    "Total shipping": "total_shipping",
    "Total tax": "total_tax",
    "Total discount": "total_discount",
    "Discount code": "discount_code",
    "Source": "source",
    "Note": "note",
    "Private notes": "private_notes",
}

df = df_raw.rename(columns=rename).copy()
df["platform"] = "bigcartel"

# =========================
# Datetime parse (format explicite)
# =========================
df["time_clean"] = df["time"].astype(str).str.replace(r"\s*CET|\s*CEST", "", regex=True)
df["sale_datetime"] = pd.to_datetime(
    df["date"].astype(str) + " " + df["time_clean"].astype(str),
    format="%Y-%m-%d %I:%M %p",
    errors="coerce",
)

# Numeric safe
for c in ["item_total", "total_shipping", "total_tax", "total_discount"]:
    if c in df.columns:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)

if "total_price" in df.columns:
    df["total_price"] = pd.to_numeric(df["total_price"], errors="coerce")  # pas de fillna



# =========================
# Parse Items -> items_df (1 ligne = 1 item)
# =========================
def split_items_blocks(items_str: str) -> list[str]:
    if not isinstance(items_str, str) or not items_str.strip():
        return []
    s = items_str.strip()
    if s.count("product_name:") <= 1:
        return [s]
    parts = re.split(r"(?=product_name:)", s)
    return [p.strip(" ,;\n\t") for p in parts if p.strip()]

def parse_item_block(block: str) -> dict:
    data = {}
    for piece in block.split("|"):
        if ":" not in piece:
            continue
        k, v = piece.split(":", 1)
        data[k.strip()] = v.strip()

    return {
        "raw_product_name": data.get("product_name"),
        "raw_option_name": data.get("product_option_name"),
        "quantity": pd.to_numeric(data.get("quantity", 1), errors="coerce"),
        "unit_price": pd.to_numeric(data.get("price"), errors="coerce"),
        "line_total": pd.to_numeric(data.get("total"), errors="coerce"),
    }

rows = []
for _, r in df.iterrows():
    blocks = split_items_blocks(r.get("items_raw", ""))
    for b in blocks:
        item = parse_item_block(b)
        rows.append({**r.to_dict(), **item})

items_df = pd.DataFrame(rows)

if items_df.empty:
    raise ValueError("items_df est vide. Vérifie la colonne Items / items_raw.")

items_df["quantity"] = items_df["quantity"].fillna(1).astype(int)
items_df["line_total"] = items_df["line_total"].fillna(items_df["unit_price"] * items_df["quantity"])

# ID stable de ligne
items_df["sale_line_id"] = (
    items_df["order_id"].astype(str) + "-" + items_df.groupby("order_id").cumcount().astype(str)
)

# Taille extraite de l'option (A0-A5)
items_df["size"] = (
    items_df["raw_option_name"]
    .astype(str)
    .str.extract(r"\b(A0|A1|A2|A3|A4|A5)\b", expand=False)
)



def load_supplier_costs(path_csv: str) -> pd.DataFrame:
    # Lecture robuste encodage
    try:
        sup = pd.read_csv(path_csv, encoding="utf-8-sig")
    except UnicodeDecodeError:
        sup = pd.read_csv(path_csv, encoding="cp1252")

    # Nettoyage mojibake simple (Ã© etc.)
    def fix_mojibake(series: pd.Series) -> pd.Series:
        mask = series.astype(str).str.contains("Ã|Â|â‚¬|â€™", na=False)
        out = series.copy()
        out.loc[mask] = (
            out.loc[mask]
            .astype(str)
            .str.encode("latin1", errors="ignore")
            .str.decode("utf-8", errors="ignore")
        )
        return out

    for c in ["Boutique", "commande", "Total"]:
        if c in sup.columns:
            sup[c] = fix_mojibake(sup[c])

    # Ignore Commandes personnelles
    sup = sup[sup["Boutique"].astype(str).str.strip() != "Commandes personnelles"].copy()

    # Normalise order id (enlève #)
    sup["supplier_order_id"] = sup["commande"].astype(str).str.strip().str.lstrip("#")

    # Parse montant + devise depuis "Total"
    # Ex: "C$ 47.71" / "€14.69" / "â‚¬14.69" (après fix, souvent €)
    def parse_amount_currency(x: str):
        if not isinstance(x, str) or not x.strip():
            return (pd.NA, pd.NA)
        s = x.strip()

        # devise
        currency = None
        if "C$" in s:
            currency = "CAD"
        elif "€" in s:
            currency = "EUR"

        # montant (prend le premier nombre)
        m = re.search(r"(-?\d+(?:[.,]\d+)?)", s)
        if not m:
            return (pd.NA, currency)
        amt = m.group(1).replace(",", ".")
        return (float(amt), currency)

    parsed = sup["Total"].apply(parse_amount_currency)
    sup["supplier_cost_amount"] = parsed.apply(lambda t: t[0])
    sup["supplier_cost_currency"] = parsed.apply(lambda t: t[1])

    # On ne garde que les colonnes utiles
    return sup[["supplier_order_id", "supplier_cost_amount", "supplier_cost_currency", "Boutique"]]

SUPPLIER_PATH = str(ROOT / "data_raw" / "orders_export.csv")
supplier = load_supplier_costs(SUPPLIER_PATH)

# Normalise order_id côté BigCartel aussi (au cas où)
df["order_id_norm"] = df["order_id"].astype(str).str.strip().str.lstrip("#")

# Merge sur commande
df = df.merge(
    supplier,
    how="left",
    left_on="order_id_norm",
    right_on="supplier_order_id"
)

# Report non match (très utile)
unmatched = df[df["supplier_cost_amount"].isna()][["order_id", "order_id_norm"]].drop_duplicates()
if len(unmatched) > 0:
    print("\n⚠️ Commandes BigCartel sans coût fournisseur matché (extraits):")
    print(unmatched.head(30).to_string(index=False))

# Injecte le coût fournisseur sur items_df via order_id
items_df["order_id_norm"] = items_df["order_id"].astype(str).str.strip().str.lstrip("#")

items_df = items_df.merge(
    df[[
        "order_id_norm",
        "supplier_cost_amount",
        "supplier_cost_currency",
    ]],
    how="left",
    on="order_id_norm"
)



def order_total_charged(items_df: pd.DataFrame) -> pd.Series:
    """
    Total réellement facturé au client.
    Priorité: reconstruction à partir des composants (item_total + shipping + tax - discount),
    car c'est stable même si total_price est mal parsé.
    Fallback: total_price si composants absents.
    """
    needed = ["item_total", "total_shipping", "total_tax", "total_discount"]
    if all(c in items_df.columns for c in needed):
        item_total = pd.to_numeric(items_df["item_total"], errors="coerce").fillna(0.0)
        shipping = pd.to_numeric(items_df["total_shipping"], errors="coerce").fillna(0.0)
        tax = pd.to_numeric(items_df["total_tax"], errors="coerce").fillna(0.0)
        discount = pd.to_numeric(items_df["total_discount"], errors="coerce").fillna(0.0)
        return item_total + shipping + tax - discount

    # fallback
    if "total_price" in items_df.columns:
        return pd.to_numeric(items_df["total_price"], errors="coerce").fillna(0.0)

    return items_df.groupby("order_id_norm")["line_total"].transform("sum")


def order_total_for_stripe(items_df: pd.DataFrame) -> pd.Series:
    """
    Base Stripe: en général Stripe prend sur le montant payé (donc pareil que total facturé).
    Si tu veux exclure tax, adapte ici.
    """
    return order_total_charged(items_df)



# Répartit le coût fournisseur par item au prorata du line_total dans la commande
items_df["order_items_total"] = items_df.groupby("order_id_norm")["line_total"].transform("sum").replace({0: pd.NA})
# CA commande (montant réellement facturé)
# si total_price est NaN, on reconstruit (robuste)
items_df["order_total_charged"] = order_total_charged(items_df)

items_df["revenue_allocated"] = (
    items_df["order_total_charged"] * (items_df["line_total"] / items_df["order_items_total"])
).fillna(0.0)

# ---- Coût fournisseur alloué par item (prorata line_total)
items_df["supplier_cost_allocated"] = (
    items_df["supplier_cost_amount"] * (items_df["line_total"] / items_df["order_items_total"])
).fillna(0.0)

# ---- Impôt sur CA (12.3% du CA réellement facturé et alloué)
items_df["tax_ca"] = (items_df["revenue_allocated"] * TAX_CA_PCT).fillna(0.0)


items_df["order_total_for_stripe"] = order_total_for_stripe(items_df)
items_df["stripe_fee_order"] = (items_df["order_total_for_stripe"] * STRIPE_FEE_PCT) + STRIPE_FEE_FIXED


# Allocation Stripe par item au prorata line_total
items_df["stripe_fee_allocated"] = items_df["stripe_fee_order"] * (items_df["line_total"] / items_df["order_items_total"])
items_df["stripe_fee_allocated"] = items_df["stripe_fee_allocated"].fillna(0.0)

# Profit net (sans prod poster par taille, ici on utilise uniquement coût fournisseur + stripe + impôt CA)
items_df["net_profit"] = (
    items_df["revenue_allocated"]
    - items_df["supplier_cost_allocated"]
    - items_df["stripe_fee_allocated"]
    - items_df["tax_ca"]
)

items_df["net_margin"] = items_df["net_profit"] / items_df["revenue_allocated"].replace({0: pd.NA})


# =========================
# Export CSV
# =========================
orders_out_path = OUT_DIR / "orders_clean_posters.csv"
lines_out_path = OUT_DIR / "sale_lines_clean_posters.csv"

orders_cols = [
    "platform","order_id","sale_datetime","transaction_id","payment_status",
    "shipping_status","shipping_method","buyer_first_name","buyer_last_name",
    "buyer_email","buyer_phone","ship_addr1","ship_addr2","ship_city","ship_state",
    "ship_zip","ship_country","currency","item_count","item_total","total_shipping",
    "total_tax","total_discount","discount_code","total_price","source"
]
orders_cols = [c for c in orders_cols if c in df.columns]
orders_clean = df[orders_cols].drop_duplicates(subset=["order_id"]).copy()
orders_clean["order_id"] = orders_clean["order_id"].astype(str)
orders_clean.to_csv(orders_out_path, index=False, encoding="utf-8-sig")

lines_cols = [
    "sale_line_id","platform","order_id","sale_datetime","buyer_email",
    "raw_product_name","raw_option_name","size","quantity","unit_price","line_total",
    "currency","total_shipping","total_tax","total_discount","total_price","order_total_for_stripe", "supplier_cost_allocated",
    "stripe_fee_allocated",
    "tax_ca",
    "net_profit",
    "net_margin",
    "supplier_cost_currency", "order_total_charged", "revenue_allocated",
]
lines_cols = [c for c in lines_cols if c in items_df.columns]
sale_lines_clean = items_df[lines_cols].copy()
sale_lines_clean.to_csv(lines_out_path, index=False, encoding="utf-8-sig")

print("\n✅ Export terminé")
print(" -", orders_out_path)
print(" -", lines_out_path)
print(f"📊 {len(orders_clean)} commandes / {len(sale_lines_clean)} lignes items")



