"""
Point d'entrée principal de l'application CAD Studio.
Démarre la boucle d'événements Qt et affiche l'interface utilisateur.
"""

from __future__ import annotations
import sys
import os

# S'assurer que le dossier racine du projet est dans sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QCoreApplication
from src.ui.main_window import CADMainWindow


def main() -> int:
    """Fonction principale de démarrage de CAD Studio (GUI ou CLI headless)."""
    # Si des arguments de ligne de commande sont passés, router vers le CLI industriel
    cli_commands = {"audit", "create-box", "cam-5axis", "ecad-thermal", "xr-stream", "connect-ai", "--version", "-h", "--help"}
    if len(sys.argv) > 1 and any(arg in cli_commands or arg.startswith("-") for arg in sys.argv[1:]):
        from src.cli import main as cli_entry
        return cli_entry(sys.argv[1:])

    log_path = os.path.abspath("debug_run.log")
    with open(log_path, "a", encoding="utf-8") as f:
        f.write("[1/6] QCoreApplication configuring AA_ShareOpenGLContexts\n")
        f.flush()

    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)

    with open(log_path, "a", encoding="utf-8") as f:
        f.write("[2/6] Instantiating QApplication\n")
        f.flush()

    app = QApplication(sys.argv)
    app.setApplicationName("CAD Studio")
    app.setOrganizationName("Brandon CAD")

    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write("[3/6] Instantiating CADMainWindow...\n")
            f.flush()

        window = CADMainWindow()

        with open(log_path, "a", encoding="utf-8") as f:
            f.write("[4/6] CADMainWindow instantiated successfully. Showing window...\n")
            f.flush()

        window.show()
        window.raise_()
        window.activateWindow()

        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"[5/6] Window shown. isVisible={window.isVisible()}, WinID={int(window.winId())}. Starting app.exec()...\n")
            f.flush()

        ret = app.exec()

        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"[6/6] app.exec() ended with returncode {ret}\n")
            f.flush()

        return ret
    except Exception as e:
        import traceback
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"[FATAL] Launch error:\n{traceback.format_exc()}\n")
            f.flush()
        raise


if __name__ == "__main__":
    sys.exit(main())
