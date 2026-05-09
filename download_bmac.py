import os
import time
from pathlib import Path
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv()

ROOT = Path(__file__).resolve().parent
RAW_DIR = ROOT / "data_raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)
OUT_BMAC = RAW_DIR / "Extras_purchase_list.csv"

CLAIMS_URL = "https://studio.buymeacoffee.com/extras/claims"
EXPORT_URL = "https://studio.buymeacoffee.com/Rewards/exportRewardPurchasers"

def env_required(name: str) -> str:
    v = os.getenv(name)
    if not v:
        raise RuntimeError(f"Missing env var: {name}")
    return v

def shutil_move_overwrite(src: Path, dest: Path) -> None:
    import shutil
    if dest.exists():
        dest.unlink()
    shutil.move(str(src), str(dest))

def main():
    print("🌐 Fetching BuyMeACoffee...")

    user_data_dir = env_required("BMAC_USER_DATA_DIR")
    profile_dir = os.getenv("BMAC_PROFILE_DIR", "Default")
    headless = False

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            channel="chrome",
            headless=headless,
            accept_downloads=True,
            args=[
                f"--profile-directory={profile_dir}",
                "--disable-features=DestroyProfileOnBrowserClose",
            ],
        )

        try:
            page = context.new_page()

            # 1) Va sur la page claims (ça permet aussi de vérifier si t'es loggé)
            page.goto(CLAIMS_URL, wait_until="domcontentloaded")

            # 2) Si tu n'es pas loggé, tu fais le login/captcha une fois
            if "login" in page.url.lower() or "sign" in page.url.lower():
                print("\n🔐 BMAC: tu n'es pas loggé dans ce profil.")
                print("➡️ Connecte-toi dans la fenêtre qui vient de s'ouvrir (captcha manuel si besoin).")
                print("➡️ Une fois connecté et que la page claims s'affiche, reviens ici.")
                input("Appuie Entrée pour lancer l'export...")

                page.goto(CLAIMS_URL, wait_until="domcontentloaded")

            # 3) Déclenche le download via l'URL d'export
            print(f"⬇️ Export CSV: {EXPORT_URL}")

            with page.expect_download(timeout=15000) as dl_info:
                try:
                    page.goto(EXPORT_URL)
                except Exception as e:
                    # Comme BigCartel, Playwright peut lever "Download is starting"
                    if "Download is starting" not in str(e):
                        raise

            download = dl_info.value
            tmp_path = RAW_DIR / f"{int(time.time())}-{download.suggested_filename}"
            download.save_as(str(tmp_path))

            shutil_move_overwrite(tmp_path, OUT_BMAC)
            print(f"✅ BMAC updated: {OUT_BMAC}")

        finally:
            try:
                context.close()
            except Exception:
                pass

if __name__ == "__main__":
    main()
