import os
import time
import shutil
from pathlib import Path
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv()

# =========================
# Paths
# =========================
ROOT = Path(__file__).resolve().parent
RAW_DIR = ROOT / "data_raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)

OUT_BIGCARTEL = RAW_DIR / "orders-all.csv"

ORDERS_URL = "https://my.bigcartel.com/orders?all=true"
EXPORT_URL = "https://my.bigcartel.com/orders_exports.csv"


# =========================
# Helpers
# =========================
def env_required(name: str) -> str:
    v = os.getenv(name)
    if not v:
        raise RuntimeError(f"Missing env var: {name}")
    return v


def safe_goto(page, url: str):
    """
    BigCartel peut relancer une navigation automatiquement.
    On ignore l'erreur 'interrupted by another navigation'.
    """
    try:
        page.goto(url, wait_until="domcontentloaded")
    except Exception as e:
        msg = str(e)
        if "interrupted by another navigation" in msg:
            return
        raise


def cleanup_variants():
    """
    Supprime orders-all (2).csv, orders-all 3.csv etc.
    """
    for p in RAW_DIR.glob("orders-all*.csv"):
        if p.name != "orders-all.csv":
            try:
                p.unlink()
            except Exception:
                pass


import os
import time
from pathlib import Path

def overwrite_file(src: Path, dest: Path):
    """
    Remplacement atomique autant que possible.
    Plus fiable que unlink + move sur Windows.
    """
    cleanup_variants()

    try:
        os.replace(str(src), str(dest))
    except PermissionError:
        raise RuntimeError(
            f"❌ Impossible d'écraser {dest}\n"
            f"➡️ Le fichier est probablement ouvert dans Excel.\n"
            f"➡️ Ferme-le puis relance le script."
        )

    # attente courte pour laisser iCloud stabiliser le fichier
    for _ in range(20):
        if dest.exists() and dest.stat().st_size > 0:
            return
        time.sleep(0.25)

    raise RuntimeError(f"❌ Le fichier final n'est pas visible après remplacement: {dest}")

# =========================
# Main
# =========================
def main():
    user_data_dir = env_required("CHROME_USER_DATA_DIR")
    profile_dir = os.getenv("CHROME_PROFILE_DIR", "Profile 2")
    headless = False

    print("🌐 Fetching BigCartel (my.bigcartel.com)...")

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=headless,
            accept_downloads=True,
            args=[f"--profile-directory={profile_dir}"],
        )

        try:
            page = context.new_page()

            # 1️⃣ Ouvre Orders
            safe_goto(page, ORDERS_URL)

            # 2️⃣ Login si nécessaire
            if "login" in page.url.lower():
                print("\n🔐 Connecte-toi dans la fenêtre BigCartel.")
                print("➡️ Une fois la liste des commandes visible, reviens ici.")
                input("Appuie Entrée pour lancer l'export CSV...")
                safe_goto(page, ORDERS_URL)

            # 3️⃣ Download CSV
            print(f"⬇️ Export CSV: {EXPORT_URL}")

            with page.expect_download(timeout=60000) as dl_info:
                try:
                    page.goto(EXPORT_URL)
                except Exception as e:
                    # Playwright lève souvent "Download is starting"
                    if "Download is starting" not in str(e):
                        raise

            download = dl_info.value

            tmp_path = RAW_DIR / f"_tmp_bigcartel_{int(time.time())}.csv"
            download.save_as(str(tmp_path))

            # 4️⃣ Overwrite propre
            overwrite_file(tmp_path, OUT_BIGCARTEL)

            print(f"✅ BigCartel updated: {OUT_BIGCARTEL}")

            print("📁 Vérification dossier data_raw :")
            for p in sorted(RAW_DIR.glob("orders-all*.csv")):
                try:
                    print(f" - {p.name} ({p.stat().st_size} bytes)")
                except Exception:
                    print(f" - {p.name}")

        finally:
            try:
                context.close()
            except Exception:
                pass


if __name__ == "__main__":
    main()