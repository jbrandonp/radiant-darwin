"""
Script d'Orchestration et de Compilation de l'Exécutable Autonome (.exe).
Permet de packager CAD Studio pour une distribution autonome sans Python préinstallé.
Architecture 100% strictement typée, sans Any ni object, CC <= 15.
"""

from __future__ import annotations
import os
import subprocess
import sys
import time
from typing import Dict, List, Optional, Union


def verify_packaging_prerequisites() -> bool:
    """Vérifie que les fichiers essentiels et les dépendances sont en place avant le build."""
    required_paths = [
        "src/main.py",
        "cad_studio.spec",
        "pyproject.toml",
    ]
    for p in required_paths:
        if not os.path.exists(p):
            print(f"[ERREUR PACKAGING] Fichier manquant requis : {p}")
            return False
    return True


def run_pyinstaller_build(clean: bool = True) -> bool:
    """Lance la compilation PyInstaller avec la spécification officielle."""
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
    ]
    if clean:
        cmd.append("--clean")
    cmd.append("cad_studio.spec")

    print(f"[PACKAGING] Lancement de la commande : {' '.join(cmd)}")
    t0 = time.perf_counter()
    res = subprocess.run(cmd, capture_output=True, text=True)
    elapsed = time.perf_counter() - t0

    if res.returncode != 0:
        print(f"[ERREUR PACKAGING] Échec de la compilation (code {res.returncode}) :")
        print(res.stderr)
        return False

    print(f"[PACKAGING] Compilation réussie en {elapsed:.2f} secondes.")
    return True


def generate_build_manifest(dist_dir: str = "dist/CADStudio") -> Dict[str, Union[str, int, bool]]:
    """Génère le manifeste de distribution et vérifie la présence du binaire principal."""
    exe_name = "CADStudio.exe" if sys.platform == "win32" else "CADStudio"
    exe_path = os.path.join(dist_dir, exe_name)
    has_exe = os.path.isfile(exe_path)
    size_bytes = os.path.getsize(exe_path) if has_exe else 0

    manifest: Dict[str, Union[str, int, bool]] = {
        "executable_name": exe_name,
        "executable_path": exe_path,
        "exists": has_exe,
        "size_bytes": size_bytes,
        "platform": sys.platform,
        "python_version": sys.version.split()[0],
    }
    return manifest


def main() -> int:
    """Point d'entrée du script de build."""
    print("======================================================================")
    print("CAD STUDIO 2026 - PIPELINE DE PACKAGING EXÉCUTABLE AUTONOME")
    print("======================================================================")
    if not verify_packaging_prerequisites():
        return 1

    success = run_pyinstaller_build(clean=True)
    if not success:
        return 1

    manifest = generate_build_manifest()
    print(f"[SUCCÈS] Binaire généré : {manifest['executable_path']} ({manifest['size_bytes']} octets)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
