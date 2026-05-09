from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def run_step(py_exe: str, script_path: Path, *, optional: bool = False, fallback_file: Path | None = None) -> None:
    print("\n" + "=" * 80)
    print(f"▶ Running: {script_path.name}")
    print("=" * 80)

    if not script_path.exists():
        raise FileNotFoundError(f"Script introuvable: {script_path}")

    result = subprocess.run(
        [py_exe, str(script_path)],
        cwd=str(script_path.parent),
        check=False,
    )

    if result.returncode == 0:
        print(f"✅ OK: {script_path.name}")
        return

    # --- erreur ---
    if optional:
        print(f"⚠️ WARNING: {script_path.name} a échoué (code={result.returncode})")

        if fallback_file is not None:
            if fallback_file.exists():
                print(f"➡️ Fallback: on continue en utilisant le fichier existant : {fallback_file}")
                return
            else:
                # step optional mais pas de fallback dispo -> on stop
                raise RuntimeError(
                    f"❌ {script_path.name} a échoué et aucun fallback n'existe.\n"
                    f"Fichier attendu introuvable : {fallback_file}"
                )

        print("➡️ Step marqué optional : on continue quand même.")
        return

    raise RuntimeError(f"❌ Échec sur {script_path.name} (code={result.returncode})")


def run_streamlit(py_exe: str, app_path: Path) -> None:
    print("\n" + "=" * 80)
    print("▶ Launching Streamlit")
    print("=" * 80)

    if not app_path.exists():
        raise FileNotFoundError(f"app.py introuvable: {app_path}")

    subprocess.run(
        [py_exe, "-m", "streamlit", "run", str(app_path)],
        cwd=str(app_path.parent),
        check=False,
    )


def main() -> None:
    root = Path(__file__).resolve().parent
    py_exe = sys.executable

    # chemins fichiers "fallback"
    bmac_fallback = root / "data_raw" / "Extras_purchase_list.csv"

    steps = [
        # téléchargements
        # {"path": root / "download_bigcartel.py", "optional": False},
        # {
        #     "path": root / "download_bmac.py",
        #     "optional": True,                 # ✅ ne casse plus la pipeline
        #     "fallback_file": bmac_fallback,   # ✅ utilise le dernier CSV si dispo
        # },
        # {"path": root / "download_printful.py", "optional": False},

        # transformations
        {"path": root / "poster.py", "optional": False},
        {"path": root / "fond_decran.py", "optional": False},
        {"path": root / "merge_and_charts.py", "optional": False},
    ]

    for step in steps:
        run_step(
            py_exe,
            step["path"],
            optional=step.get("optional", False),
            fallback_file=step.get("fallback_file"),
        )

    run_streamlit(py_exe, root / "app_updated.py")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("\n" + "!" * 80)
        print("STOP: une étape a échoué.")
        print(e)
        print("!" * 80)
        raise
