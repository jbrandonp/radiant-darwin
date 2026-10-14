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
    cli_commands = {"audit", "create-box", "cam-5axis", "ecad-thermal", "xr-stream", "--version", "-h", "--help"}
    if len(sys.argv) > 1 and any(arg in cli_commands or arg.startswith("-") for arg in sys.argv[1:]):
        from src.cli import main as cli_entry
        return cli_entry(sys.argv[1:])

    # Activer le partage des contextes OpenGL
    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)

    app = QApplication(sys.argv)
    app.setApplicationName("CAD Studio")
    app.setOrganizationName("Brandon CAD")

    try:
        window = CADMainWindow()
        window.show()
        window.raise_()
        window.activateWindow()

        with open("app_launch.log", "w", encoding="utf-8") as f:
            f.write(f"App started successfully. Window handle: {int(window.winId())}\n")

        return app.exec()
    except Exception as e:
        import traceback
        with open("app_launch.log", "w", encoding="utf-8") as f:
            f.write(f"Launch error:\n{traceback.format_exc()}\n")
        raise


if __name__ == "__main__":
    sys.exit(main())
