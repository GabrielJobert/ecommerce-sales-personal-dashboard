import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent
RAW_DIR = ROOT / "data_raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)

OUT_PRINTFUL = RAW_DIR / "orders_export.csv"
API_BASE = "https://api.printful.com"


def env_required(name: str) -> str:
    v = os.getenv(name)
    if not v:
        raise RuntimeError(f"Missing env var: {name}")
    return v


def to_float(x: Any) -> float:
    try:
        return float(x)
    except Exception:
        return 0.0


def build_session(token: str) -> requests.Session:
    s = requests.Session()
    s.headers.update(
        {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "User-Agent": "WorkflowV0/1.0",
        }
    )
    return s


def request_json(
    session: requests.Session,
    url: str,
    params: Optional[dict] = None,
    retries: int = 8,
) -> dict:
    """
    Wrapper robuste Printful:
    - gère 429 (Retry-After si présent)
    - backoff exponentiel sur erreurs transient
    """
    backoff = 1.0
    for attempt in range(retries):
        r = session.get(url, params=params, timeout=60)

        # Rate limit
        if r.status_code == 429:
            ra = r.headers.get("Retry-After")
            sleep_s = float(ra) if ra and ra.isdigit() else backoff
            time.sleep(sleep_s)
            backoff = min(backoff * 2, 30)
            continue

        # Transient errors
        if r.status_code in (502, 503, 504):
            time.sleep(backoff)
            backoff = min(backoff * 2, 30)
            continue

        r.raise_for_status()
        return r.json()

    # Si on arrive ici, on a échoué
    r.raise_for_status()
    return {}  # jamais atteint


def fetch_all_order_summaries(session: requests.Session) -> List[Dict[str, Any]]:
    """
    Récupère la liste de toutes les commandes (rapide).
    """
    limit = 100
    offset = 0
    all_orders: List[Dict[str, Any]] = []

    while True:
        payload = request_json(
            session,
            f"{API_BASE}/orders",
            params={"limit": limit, "offset": offset},
        )
        result = payload.get("result") or []
        if not result:
            break

        all_orders.extend(result)

        if len(result) < limit:
            break
        offset += limit

    return all_orders


def fetch_order_detail(session: requests.Session, order_id: int) -> Optional[Dict[str, Any]]:
    """
    Récupère le détail d'une commande (pour costs.total etc.).
    """
    payload = request_json(session, f"{API_BASE}/orders/{order_id}")
    return payload.get("result")


def order_to_export_row(order: Dict[str, Any]) -> Dict[str, Any]:
    """
    Format CSV attendu :
    Boutique,commande,Statut,Total,Date,Adresse
    """
    costs = order.get("costs") or {}
    total_cost = costs.get("total", 0.0)

    currency = (order.get("currency") or "EUR").upper()
    currency_symbol = "€" if currency == "EUR" else ("C$" if currency == "CAD" else currency)

    # external_id = id BigCartel si tu l'envoies à Printful comme ça
    ext = str(order.get("external_id") or "").strip()
    commande = f"#{ext}" if ext and not ext.startswith("#") else ext

    recip = order.get("recipient") or {}
    address = ", ".join(
        [x for x in [
            recip.get("name"),
            recip.get("address1"),
            recip.get("address2"),
            recip.get("city"),
            recip.get("state_code") or recip.get("state_name") or recip.get("state"),
            recip.get("zip"),
            recip.get("country_code") or recip.get("country_name") or recip.get("country"),
        ] if x]
    )

    return {
        "Boutique": "Ewilan" if commande else "Printful",  # optionnel, tu peux mettre "Printful"
        "commande": commande,
        "Statut": str(order.get("status") or ""),
        "Total": f"{currency_symbol}{to_float(total_cost):.2f}",
        "Date": str(order.get("created") or ""),
        "Adresse": address or "x",
    }


def main():
    print("🌐 Fetching Printful (stable, no date filter)...")
    token = env_required("PRINTFUL_TOKEN")
    session = build_session(token)

    # 1) Liste rapide
    summaries = fetch_all_order_summaries(session)
    print(f"📦 Found Printful orders: {len(summaries)}")

    order_ids = [o.get("id") for o in summaries if o.get("id")]
    if not order_ids:
        df_empty = pd.DataFrame(columns=["Boutique", "commande", "Statut", "Total", "Date", "Adresse"])
        df_empty.to_csv(OUT_PRINTFUL, index=False, encoding="utf-8-sig")
        print(f"✅ Printful updated: {OUT_PRINTFUL} (0 rows)")
        return

    # 2) Détails (limités en parallèle pour éviter 429)
    max_workers = int(os.getenv("PRINTFUL_WORKERS", "4"))  # 2-4 recommandé
    rows: List[Dict[str, Any]] = []

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(fetch_order_detail, session, oid): oid for oid in order_ids}

        done = 0
        for fut in as_completed(futures):
            oid = futures[fut]
            try:
                detail = fut.result()
            except Exception as e:
                print(f"❌ Printful error for order_id={oid}: {e}")
                continue

            if detail:
                rows.append(order_to_export_row(detail))

            done += 1
            if done % 50 == 0:
                print(f"… {done}/{len(order_ids)}")

    # 3) Export CSV attendu
    df = pd.DataFrame(rows)
    if df.empty:
        df = pd.DataFrame(columns=["Boutique", "commande", "Statut", "Total", "Date", "Adresse"])

    df = df[["Boutique", "commande", "Statut", "Total", "Date", "Adresse"]]
    df.to_csv(OUT_PRINTFUL, index=False, encoding="utf-8-sig")

    print(f"✅ Printful updated: {OUT_PRINTFUL} ({len(df)} rows)")
    print(f"ℹ️ Workers used: {max_workers}")


if __name__ == "__main__":
    main()
