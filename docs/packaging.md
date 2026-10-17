# Guide de Packaging et de Distribution Autonome (CAD Studio)

Ce guide décrit la procédure de compilation de **CAD Studio (`radiant-darwin`)** en exécutable autonome (`.exe` sous Windows ou binaire Linux/macOS) sans nécessiter l'installation de Python sur la machine cible.

---

## 📋 Prérequis
- Python 3.10+ dans l'environnement virtuel `.venv`
- Dépendances du projet installées (`pip install -e .` ou `uv sync`)
- PyInstaller (`pip install pyinstaller`)

---

## 🚀 Compilation en un Clic

Pour lancer la compilation complète de l'application :

```bash
# Via le script d'orchestration dédié :
.venv\Scripts\python.exe scripts/build_standalone_exe.py

# Ou directement via PyInstaller :
.venv\Scripts\pyinstaller.exe --clean cad_studio.spec
```

L'exécutable et ses bibliothèques dynamiques (Qt, Manifold3D, OpenGL) seront générés dans le dossier :
```text
dist/
└── CADStudio/
    ├── CADStudio.exe     <-- Exécutable autonome à double-cliquer
    ├── _internal/        <-- Bibliothèques C++, shaders et dépendances
    └── docs/             <-- Documentation embarquée
```

---

## 🛠️ Structure de la Spécification (`cad_studio.spec`)

- **Point d'entrée :** `src/main.py`
- **Fenêtrage :** `console=False` (pas de fenêtre de terminal noire au lancement).
- **Inclusions de données :** `src/`, `docs/`, shaders et profils.
- **Imports dynamiques intégrés :**
  - Moteur d'interface : `PySide6` (Widgets, OpenGL, Core, Gui)
  - Moteur géométrique : `manifold3d`, `trimesh`, `scipy`, `numpy`
  - Modules internes : `src.io`, `src.catalog`, `src.system`, `src.viewport`, `src.core`, `src.cam`, `src.fea`

---

## 📦 Création d'un Installateur Windows (Inno Setup / NSIS)

Pour générer un installateur `Setup_CADStudio.exe` avec raccourcis Bureau et Menu Démarrer :
1. Installer [Inno Setup](https://jrsoftware.org/isdl.php).
2. Pointer le répertoire source sur `dist/CADStudio/`.
3. Définir `dist/CADStudio/CADStudio.exe` comme application principale.
