# CAD Studio (Radiant-Darwin) — Next-Gen Parametric 3D CAD/CAE/CAM Suite & AI Copilot

[![Python Versions](https://img.shields.io/badge/Python-3.10%20%7C%203.11%20%7C%203.12-3776AB.svg?logo=python&logoColor=white)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![GUI: PySide6](https://img.shields.io/badge/GUI-Qt6%20PySide6-41CD52.svg?logo=qt&logoColor=white)](https://doc.qt.io/qtforpython/)
[![Kernel: Manifold3D](https://img.shields.io/badge/Kernel-Manifold3D%20C%2B%2B-FF6F00.svg)](https://github.com/elalish/manifold)
[![Quality Gate](docs/badges/quality-gate.svg)](docs/audit_report.html)
[![Strict Typing](docs/badges/strict-typing.svg)](docs/audit_report.html)
[![Maintainability](docs/badges/maintainability.svg)](docs/audit_report.html)
[![Tests](docs/badges/tests.svg)](docs/audit_report.html)
[![Protocol: MCP](https://img.shields.io/badge/AI-Model%20Context%20Protocol-8A2BE2.svg)](https://modelcontextprotocol.io)

**CAD Studio (Radiant-Darwin)** est une suite logicielle paramétrique industrielle 3D unifiée de nouvelle génération combinant la puissance d'**Autodesk Fusion 360**, l'extensibilité open-source de **FreeCAD**, et l'intégration native d'un **Copilote IA autonome (protocole MCP / Model Context Protocol)**.

Elle regroupe au sein d'une architecture modulaire et fortement typée (zéro `Any`, zéro `object`) l'ensemble des disciplines de l'ingénierie mécanique, de la conception géométrique avancée jusqu'à la fabrication numérique et l'analyse multi-physique.

---

## 🌟 Architecture & Pôles Technologiques

```mermaid
graph TD
    subgraph Core ["Noyau Géométrique & Paramétrique"]
        M3D["Manifold3D (Noyau CSG C++)"]
        NEXUS["Nexus Kernel (NURBS, Predicates, Dual Quat)"]
        DAG["Arbre DAG & Timeline Rollback"]
        SOLV["Solveur Esquisse 2D (SciPy TRF)"]
        FX["Moteur Formules fx (AST Sécurisé)"]
    end

    subgraph Engineering ["Ateliers d'Ingénierie & Multi-Physique"]
        SM["Tôlerie Industrielle (Facteur K, DXF)"]
        ASS["Assemblage & Cinématique"]
        FEA["Simulation FEA & Ponts Gmsh/CalculiX"]
        CAM["CAM 2.5D & 5-Axes RTCP Anti-Gouge"]
        DRW["Mise en Plan ISO 128 (SVG)"]
        PBR["Rendu Photoréaliste Raytracing PBR"]
        SPEC["Spécialisé (Aéro, BIM, ECAD, Robotique)"]
    end

    subgraph AI ["Intelligence Artificielle & Automatisation"]
        MCP["Serveur MCP STDIO (Claude, Cursor, Copilot)"]
        SYNTH["Synthétiseur de Formes & Scripting"]
        VIS["Inspection Visuelle & Auto-Guérison"]
        UI_AI["Palette de Commandes & Copilot Dock"]
    end

    Core --> Engineering
    AI <--> Core
    AI <--> Engineering
```

---

## 🚀 Fonctionnalités Majeures

### 1. 🛠️ Modélisation Solide & Noyau Géométrique Hybride
- **Noyau double Manifold3D + Nexus B-Rep** : Garantit des solides 3D "watertight" (variétés étanches 2-manifold) et prévient les dégénérescences de volume nul.
- **Opérations d'ingénierie complètes** :
  - Primitives paramétriques (Boîte, Cylindre, Sphère, Cône, Tore).
  - Extrusion linéaire, Révolution 360°, Perçage calibré (Hole Tool), Coque (Shell), Matrices linéaires et circulaires, Symétrie miroir.
  - Arbre de construction chronologique (**Timeline Fusion 360**) avec curseur de retour dans le temps (**Rollback Slider**).
  - Congés de raccordement par sphère roulante (**Rolling Ball Blend**), modélisation directe (**Push-Pull**), et structures allégées (**Generative Lattices**).

### 2. 📐 Esquisse 2D & Solveur Non-Linéaire
- Solveur géométrique basé sur l'algorithme des Moindres Carrés TRF (*Trust Region Reflective*) de SciPy.
- Contraintes : Coïncidence, Horizontalité, Verticalité, Distance cotée, Points d'ancrage fixes, Tangence.
- Contrôle strict du nombre maximal d'itérations et prévention des blocages sur croquis sur-contraints.

### 3. 📑 Tôlerie Industrielle (Sheet Metal)
- Calcul de la fibre neutre par **Facteur K** ($K = 0.44$ acier standard).
- Calcul analytique du développement d'arc (*Bend Allowance*) et de la déduction au pli (*Bend Deduction*).
- Dépliage automatique en flan plat (**Flat Pattern**).
- Export AutoCAD DXF R12 avec calques normalisés `CUT` (découpe laser CNC) et `BEND` (lignes de pliage).

### 4. 🔗 Assemblages Cinématiques & Détection de Collisions
- Liaisons normalisées : Rigide, Pivot (1 DDL), Glissière (1 DDL).
- Détection volumique des interférences physiques par intersection CSG booléenne exacte.

### 5. 📊 Simulation Multi-Physique & Éléments Finis (FEA)
- Calcul statique de la **contrainte équivalente de von Mises** $\sigma_{vm}$, de la flèche maximale et du facteur de sécurité mécanique.
- Rendu direct de la cartographie de contrainte (gradient couleur arc-en-ciel) sur le maillage dans le Viewport 3D.
- Passerelles d'intégration pour solveurs externes : **Gmsh**, **CalculiX**, et **OpenFOAM**.

### 6. ✂️ Fabrication Assistée par Ordinateur (CAM / FAO)
- Génération de parcours d'outils 2.5D (Surfaçage, Contournage ébauche/finition).
- CAM 5-axes simultané avec gestion cinématique RTCP (*Rotational Tool Center Point*) et évitement automatique des gouges.
- Placement automatique de fibres composites (**AFP / Automated Fiber Placement**).
- Contrôle qualité métrologique CMM avec recalage géométrique ICP (*Iterative Closest Point*).
- Post-processeur G-Code universel compatible ISO/Fanuc, GRBL, LinuxCNC, et Mach3.

### 7. 📋 Dessin Technique Normalisé ISO 128
- Génération automatique des 4 vues orthogonales (Face, Dessus, Droite, Isométrique 3D).
- Lignes d'arêtes visibles, axes de symétrie, cotations dimensionnelles automatiques.
- Cartouche d'ingénierie normalisé et export vectoriel SVG haute résolution.

### 8. 📸 Studio de Rendu Photoréaliste PBR
- Matériaux optiques réalistes (*Physically Based Rendering*) avec formule de **Fresnel-Schlick**.
- Bibliothèque de matériaux : Aluminium brossé, Chrome, Or, Titane, Cuivre, Fibre de carbone, Plastiques ABS.
- Studio d'illumination 3-points (Key, Fill, Rim lights) et export d'images PNG.

### 9. 🤖 Copilote IA Autonome & Serveur MCP (Model Context Protocol)
- **Standard MCP STDIO** : Branchez directement votre client IA préféré (Claude Desktop, Cursor IDE, Copilot, ChatGPT Desktop) en pointant sur la commande `cad-mcp` ou `python -m src.ai.mcp_stdio`.
- **Synthèse de formes en langage naturel** : Génération de modèles paramétriques et de scripts CSG à partir d'une simple description textuelle.
- **Auto-guérison et validation visuelle** : Analyse des erreurs de modélisation, vérification de l'étanchéité des solides et correction autonome.
- **Palette de commandes IA & Dock Copilote** intégrés à l'interface graphique Qt.

---

## 💻 Installation & Démarrage Rapide

### Prérequis
- **Python 3.10, 3.11 ou 3.12**
- Windows 10/11, Ubuntu/Debian Linux, ou macOS

### 1. Cloner le Dépôt
```bash
git clone https://github.com/jbrandonp/radiant-darwin.git
cd radiant-darwin
```

### 2. Environnement Virtuel
```bash
# Création de l'environnement virtuel
python -m venv .venv

# Activation :
# Sur Windows :
.\.venv\Scripts\activate
# Sur Linux / macOS :
source .venv/bin/activate
```

### 3. Installation du Package
```bash
# Installation en mode éditable avec dépendances de développement
pip install -e ".[dev]"
```

*Sur Linux Ubuntu/Debian, si vous exécutez dans un conteneur ou serveur sans écran :*
```bash
sudo apt-get update && sudo apt-get install -y libgl1-mesa-glx xvfb
```

---

## 🖥️ Utilisation

### Mode Interface Graphique (GUI)
Lancez l'atelier complet CAD Studio :
```bash
# Via commande console
cad-studio

# Ou via Python
python src/main.py

# Ou via les lanceurs multi-plateformes fournis :
# Windows :
launch_cad_studio.bat
# Linux / macOS :
./launch_cad_studio.sh
```

### Mode Ligne de Commande Industrielle (CLI Headless)
Idéal pour les scripts d'automatisation et les pipelines d'intégration continue :
```bash
# Afficher l'aide et la version
cad-cli --help
cad-cli --version

# Créer une pièce géométrique et l'exporter en STL
cad-cli create-box --width 50 --height 30 --depth 20 --output boitier.stl

# Générer un programme G-Code 5-axes sans gouges
cad-cli cam-5axis --output usinage_5axes.gcode

# Simuler l'échauffement Joule d'un circuit imprimé ECAD
cad-cli ecad-thermal --current 3.5

# Exécuter l'audit industriel officiel déterministe
cad-cli audit
```

### Mode Serveur IA MCP (Model Context Protocol)
Pour connecter une IA externe (Claude Desktop, Cursor, agents autonomes) :
```bash
cad-mcp
# Ou :
python -m src.ai.mcp_stdio
```

*Exemple de configuration `claude_desktop_config.json` :*
```json
{
  "mcpServers": {
    "cad-studio": {
      "command": "python",
      "args": ["-m", "src.ai.mcp_stdio"],
      "cwd": "/chemin/vers/radiant-darwin"
    }
  }
}
```

### Démonstrateur Intégral (Tous les Ateliers)
Génère automatiquement les 5 fichiers d'ingénierie dans le dossier `demo_output/` :
```bash
python demo_full_suite.py
```

---

## 🧪 Tests & Assurance Qualité Industrielle

Le projet dispose d'une suite exhaustive de tests unitaires, d'intégration et de résistance aux cas limites :

```bash
# Exécution de la suite complète de 714 tests en mode headless
pytest tests/ -v

# Vérification du Quality Gate industriel
python scripts/industrial_audit_engine.py
```

### Métriques d'Audit :
- **Tests unitaires & intégration** : 714/714 passés (100% de succès)
- **Indice Composite de Maintenabilité (ISO/IEC 25010:2023 CMI)** : **96.5 / 100 [GRADE A]**
- **Typage statique strict** : 100.00% (Strictement zéro `Any`, zéro `object` dans `src/`)
- **Complexité cognitive** : Aucune fonction n'excède le plafond de 25 (max 23)
- **Vulnérabilités de sécurité SAST** : 0 faille détectée
- **Dépendances cycliques (Tarjan)** : 0 cycle d'architecture
- **Quality Gate SonarQube Enterprise** : **PASSED (GREEN - Conforme Industriel)**

---

## 🏛️ Arborescence du Projet

```
radiant-darwin/
├── .github/
│   └── workflows/
│       └── ci.yml               # Pipeline CI/CD GitHub Actions multi-OS
├── scripts/
│   ├── industrial_audit_engine.py # Moteur d'audit déterministe ISO 25010
│   ├── multi_domain_simulation_matrix.py # Matrice Phase 1 de 8 simulations multi-physiques
│   ├── advanced_physics_simulation_matrix_phase2.py # Matrice Phase 2 (Hamiltonien, boucles fermées, BIM, PBR...)
│   ├── deep_bug_hunter.py       # Chasseur de bugs et tolérancement géométrique
│   └── multi_type_simulation_fuzzer.py # Fuzzing et stress-tests multi-physiques
├── src/
│   ├── ai/                      # Serveur MCP, pont IA, synthétiseur, auto-guérison
│   ├── assembly/                # Assemblages mécaniques et détection d'interférences
│   ├── cam/                     # FAO 2.5D, 5-axes RTCP, AFP fibre, métrologie CMM
│   ├── core/                    # Moteur solide, Manifold3D, DAG, Timeline, Nexus Kernel
│   ├── drawing/                 # Dessin technique ISO 128 et export SVG
│   ├── fea/                     # Éléments finis von Mises, ponts CalculiX et OpenFOAM
│   ├── materials/               # Base de données de matériaux, masses et centres d'inertie
│   ├── render/                  # Studio de rendu PBR, Fresnel-Schlick, raytracer
│   ├── sheetmetal/              # Tôlerie, facteur K, développée à plat, export DXF
│   ├── solver/                  # Solveur de contraintes d'esquisse 2D (SciPy TRF)
│   ├── specialized/             # Aérodynamique, BIM IFC, ECAD thermique, robotique
│   ├── ui/                      # Interface Qt Dark Fusion 360, ruban, palette IA
│   ├── viewport/                # Rendu OpenGL interactif, ViewCube, gizmos, XR LOD
│   ├── cli.py                   # Interface en ligne de commande industrielle
│   └── main.py                  # Point d'entrée principal GUI / CLI
├── tests/                       # 714 tests unitaires, d'intégration et de robustesse
├── CONTRIBUTING.md              # Guide de contribution et règles architecturales
├── LICENSE                      # Licence open-source MIT
├── pyproject.toml               # Packaging moderne PEP 517/621
├── README.md                    # Documentation complète
├── requirements.txt             # Dépendances pip
├── launch_cad_studio.bat        # Lanceur Windows
└── launch_cad_studio.sh         # Lanceur Linux/macOS
```

---

## 📄 Licence

Ce projet est sous licence **MIT**. Voir le fichier [LICENSE](LICENSE) pour plus de détails.

---

## 🤝 Contribution

Les contributions sont les bienvenues ! Veuillez consulter le fichier [CONTRIBUTING.md](CONTRIBUTING.md) pour découvrir les règles de codage et le processus de soumission de Pull Requests.
