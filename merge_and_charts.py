import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path

ROOT = Path(__file__).resolve().parent
POSTERS_PATH = ROOT / "data_transformed" / "sale_lines_clean_posters.csv"
WALLS_PATH   = ROOT / "data_transformed" / "sale_lines_clean_wallpapers.csv"

OUT_DIR = ROOT / "data_analytics"
OUT_DIR.mkdir(exist_ok=True)

posters = pd.read_csv(POSTERS_PATH, encoding="utf-8-sig")
posters["sale_datetime"] = pd.to_datetime(posters["sale_datetime"], errors="coerce")

posters_norm = pd.DataFrame({
    "sale_line_id": posters["sale_line_id"],
    "sale_datetime": posters["sale_datetime"],
    "platform": posters["platform"],
    "product_type": "poster",
    "artwork_name": posters["raw_product_name"],
    "quantity": posters["quantity"],
    "revenue": posters["revenue_allocated"],
    "costs_total": (
        posters["supplier_cost_allocated"]
        + posters["stripe_fee_allocated"]
        + posters["tax_ca"]
    ),
    "net_profit": posters["net_profit"],
    "net_margin": posters["net_margin"],
    "currency": posters["currency"],

    # descriptif utile
    "size": posters["size"],
    "option_label": posters["raw_option_name"],
    "order_id": posters["order_id"],
})

walls = pd.read_csv(WALLS_PATH, encoding="utf-8-sig")
walls["sale_datetime"] = pd.to_datetime(walls["sale_datetime"], errors="coerce")

walls_norm = pd.DataFrame({
    "sale_line_id": walls["sale_line_id"],
    "sale_datetime": walls["sale_datetime"],
    "platform": walls["platform"],
    "product_type": "wallpaper",
    "artwork_name": walls["raw_product_name"],
    "quantity": walls["quantity"],
    "revenue": walls["line_total"],
    "costs_total": walls["tax_ca"],  # pas de prod, pas de stripe sur bmac
    "net_profit": walls["net_profit"],
    "net_margin": walls["net_margin"],
    "currency": walls["currency"],

    # descriptif
    "pack_label": walls["pack_label"],
    "wallpaper_kind": walls["wallpaper_kind"],
    "customer_id": walls["customer_id"],
})

sales_all = pd.concat(
    [posters_norm, walls_norm],
    ignore_index=True
)

# Colonnes temps utiles
sales_all["date"] = sales_all["sale_datetime"].dt.date
sales_all["week"] = sales_all["sale_datetime"].dt.to_period("W").astype(str)
sales_all["month"] = sales_all["sale_datetime"].dt.to_period("M").astype(str)

OUT_MERGED = OUT_DIR / "sales_all_normalized.csv"
sales_all.to_csv(OUT_MERGED, index=False, encoding="utf-8-sig")

print("✅ Merge terminé :", OUT_MERGED)
print("Lignes :", len(sales_all))
