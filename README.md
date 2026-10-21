# CAD Studio (Radiant-Darwin) — Next-Gen Parametric 3D CAD/CAE/CAM Suite & AI Copilot

[![Python Versions](https://img.shields.io/badge/Python-3.10%20%7C%203.11%20%7C%203.12-3776AB.svg?logo=python&logoColor=white)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![GUI: PySide6](https://img.shields.io/badge/GUI-Qt6%20PySide6-41CD52.svg?logo=qt&logoColor=white)](https://doc.qt.io/qtforpython/)
[![Kernel: Manifold3D](https://img.shields.io/badge/Kernel-Manifold3D%20C%2B%2B-FF6F00.svg)](https://github.com/elalish/manifold)
[![Quality Gate: Grade A](https://img.shields.io/badge/Quality%20Gate-Grade%20A%20(96.2%2F100)-success.svg)](docs/audit_report.html)
[![Strict Typing: 100%](https://img.shields.io/badge/Strict%20Typing-100%25%20(0%20Any)-brightgreen.svg)](docs/audit_report.html)
[![Maintainability: ISO 25010](https://img.shields.io/badge/ISO%2025010-CMI%2096.2%20Grade%20A-blue.svg)](docs/audit_report.html)
[![Tests: 864 Passed](https://img.shields.io/badge/Tests-864%20Passed%20(100%25)-brightgreen.svg)](docs/audit_report.html)
[![Protocol: MCP](https://img.shields.io/badge/AI-Model%20Context%20Protocol-8A2BE2.svg)](https://modelcontextprotocol.io)

**CAD Studio (Radiant-Darwin)** est une suite logicielle paramétrique industrielle 3D unifiée de nouvelle génération combinant la puissance d'**Autodesk Fusion 360**, l'extensibilité de **FreeCAD**, et l'intégration native d'un **Copilote IA autonome (protocole MCP / Model Context Protocol)**.

Elle regroupe au sein d'une architecture modulaire et strictement typée (171 modules, 41 273 lignes de code, **100.00% sans `Any` ni `object`**) l'ensemble des disciplines de l'ingénierie mécanique : de la conception géométrique exacte (B-Rep, CSG, NURBS) jusqu'à la fabrication numérique 5-axes (CAM/RTCP), l'analyse multi-physique (FEA/CFD) et les jumeaux numériques mécatroniques.

---

## 🌟 Architecture & Pôles Technologiques

```mermaid
graph TD
    subgraph Core ["Noyau Géométrique & Paramétrique"]
        M3D["Manifold3D (Noyau CSG C++)"]
        NEXUS["Nexus Kernel (NURBS, Coons G2, B-Rep Watertight, EGC Predicates)"]
        DAG["Arbre DAG & Timeline Rollback"]
        SOLV["Solveur Esquisse 2D (SciPy TRF & Rigidité Laman)"]
        FX["Moteur Formules fx (AST Sécurisé & Dépendances)"]
    end

    subgraph Engineering ["Ateliers d'Ingénierie & Multi-Physique"]
        SM["Tôlerie Industrielle (Facteur K, Flans Plats DXF)"]
        ASS["Assemblage & Cinématique (Solveur de Mates Rodrigues & Interférences)"]
        FEA["Simulation FEA & Ponts Gmsh / CalculiX (C3D4, C3D10 Quadratique)"]
        CAM["CAM 2.5D & 5-Axes RTCP (Haas, Fanuc, Heidenhain, Siemens 840D)"]
        DRW["Mise en Plan ISO 128 (Vues Orthogonales, GD&T, SVG)"]
        PBR["Rendu Photoréaliste Raytracing PBR & Fresnel-Schlick"]
        SPEC["Spécialisé (Aéro CFD, BIM IFC4, ECAD Thermique, Robotique 6-Axes)"]
    end

    subgraph AI ["Intelligence Artificielle & Automatisation SOTA"]
        MCP["Serveur MCP STDIO (Claude, Cursor, Copilot)"]
        SYNTH["Synthétiseur de Formes & Scripts Paramétriques"]
        VIS["Inspection Visuelle, Z-Buffer & Auto-Guérison"]
        SKILLS["10 Compétences Spécialisées (.agents/skills)"]
        UI_AI["Palette de Commandes & Copilot Dock Qt"]
    end

    Core --> Engineering
    AI <--> Core
    AI <--> Engineering
```

---

## 🚀 Fonctionnalités Majeures

### 1. 🛠️ Modélisation Solide & Noyau Hybride B-Rep / CSG
- **Noyau double Manifold3D + Nexus B-Rep** : Solides 3D garantis *watertight* (variétés étanches 2-manifold), éliminant les singularités et auto-intersections.
- **Surfaces NURBS & Carreaux de Coons** : Évaluation de courbures principales (Gauss, moyenne), continuité géométrique $G^1$/$G^2$, raccordement exact avec multiplicité $p+1$ et projection paramétrique par matrice de Gram locale.
- **Prédicats Géométriques Exacts (EGC)** : Algorithmes robustes adaptatifs de Shewchuk (`orient2d`, `orient3d`, `incircle`) accélérés par FMA matériel natif (`math.fma`).
- **Opérations d'ingénierie complètes** :
  - Primitives paramétriques (Boîte, Cylindre, Sphère, Cône, Tore).
  - Extrusion linéaire, Révolution 360°, Perçage calibré (Hole Tool), Dépouille (Draft Feature), Coque (Shell), Réseaux linéaires et polaires, Miroir.
  - Arbre de construction chronologique (**Timeline Fusion 360**) avec curseur de retour dans le temps (**Rollback Slider**).
  - Congés de raccordement par sphère roulante (**Rolling Ball Blend**), modélisation directe (**Push-Pull**), et structures allégées (**TPMS Gyroid / Diamond Lattices**).

### 2. 📐 Esquisse 2D & Solveur Non-Linéaire
- Solveur géométrique basé sur l'algorithme des Moindres Carrés TRF (*Trust Region Reflective*) de SciPy et analyse de rigidité combinatoire de Laman.
- Contraintes : Coïncidence, Horizontalité, Verticalité, Distance cotée, Points d'ancrage fixes, Tangence, Angle, et symétrie.
- Prévention mathématique des singularités et gestion des croquis sur-contraints avec diagnostic des degrés de liberté.

### 3. 📑 Tôlerie Industrielle (Sheet Metal)
- Calcul de la fibre neutre par **Facteur K** ($K = 0.44$ acier standard).
- Calcul analytique du développement d'arc (*Bend Allowance*) et de la déduction au pli (*Bend Deduction*).
- Dépliage automatique en flan plat (**Flat Pattern**).
- Export AutoCAD DXF R12 avec calques normalisés `CUT` (découpe laser CNC) et `BEND` (lignes de pliage et sens de pli).

### 4. 🔗 Assemblages Cinématiques & Détection de Collisions
- Liaisons normalisées : Rigide, Pivot (1 DDL), Glissière (1 DDL), Coïncidence plane, Coaxialité, et Parallélisme (2 DDL).
- Alignement tridimensionnel par décomposition d'axe et rotation de Rodrigues préservant l'orientation naturelle.
- Détection volumique des interférences physiques par intersection CSG booléenne exacte.

### 5. 📊 Simulation Multi-Physique & Éléments Finis (FEA)
- Calcul statique et non-linéaire de la **contrainte équivalente de von Mises** $\sigma_{vm}$, des déformations principales et du facteur de sécurité mécanique.
- Éléments tétraédriques linéaires (Tet4) et quadratiques à 10 nœuds (Tet10) avec formulation isoparamétrique et jacobien strictement positif ($\det(J) > 0$).
- Cartographie couleur en direct sur le maillage dans le Viewport 3D OpenGL.
- Passerelles d'intégration pour solveurs externes : **Gmsh** (maillage volumique adaptatif), **CalculiX** (synthèse de decks `*STATIC`, `*STEP`, `*BOUNDARY`), et **OpenFOAM** (aérodynamique Navier-Stokes).

### 6. ✂️ Fabrication Assistée par Ordinateur (CAM / FAO)
- Génération de parcours d'outils 2.5D (Surfaçage zigzag, Contournage ébauche/finition, interpolation circulaire hélicoïdale).
- CAM 5-axes simultané avec gestion cinématique **RTCP** (*Rotational Tool Center Point*) et évitement automatique des gouges.
- Simulateur volumique de matière restante par voxels avec suivi incrémental ultra-rapide $O(1)$.
- Registre de post-processeurs industriels : **Siemens Sinumerik 840D**, **Fanuc**, **Haas**, **Heidenhain TNC**, et ISO standard.
- Placement automatique de fibres composites (**AFP / Automated Fiber Placement**) et métrologie CMM avec recalage géométrique ICP (*Iterative Closest Point*).

### 7. 🤖 Robotique & Jumeaux Numériques Spécialisés
- Cinématique directe et inverse pour bras robotiques sériels 6-axes avec calcul analytique du **Jacobien géométrique complet** :
  $$\mathbf{J}_i = \begin{bmatrix} \mathbf{z}_{i-1} \times (\mathbf{p}_e - \mathbf{p}_{i-1}) \\ \mathbf{z}_{i-1} \end{bmatrix}$$
- Indice de manipulabilité de Yoshikawa exact sans singularité aveugle.
- Aérodynamique compressible/incompressible, pont BIM IFC4 (murs, poutres, dalles, colonnes) et thermique ECAD PCB (échauffement Joule $I^2 R$).

### 8. 📋 Dessin Technique Normalisé ISO 128
- Génération automatique des 4 vues orthogonales (Face, Dessus, Droite, Isométrique 3D).
- Lignes d'arêtes visibles, cachées, axes de symétrie, cotations dimensionnelles automatiques et cadres de tolérancement géométrique (GD&T).
- Cartouche d'ingénierie normalisé et export vectoriel SVG haute résolution.

### 9. 📸 Studio de Rendu Photoréaliste PBR
- Matériaux optiques réalistes (*Physically Based Rendering*) avec formule de **Fresnel-Schlick**.
- Bibliothèque complète : Aluminium brossé, Chrome, Or, Titane, Cuivre, Fibre de carbone, Plastiques techniques.
- Illumination 3-points (Key, Fill, Rim lights) et export d'images haute définition.

### 10. 🧠 Copilote IA Autonome & Serveur MCP (Model Context Protocol)
- **Standard MCP STDIO** : Branchez directement votre client IA préféré (Claude Desktop, Cursor IDE, Copilot, ChatGPT Desktop) en pointant sur la commande `cad-mcp` ou `python -m src.ai.mcp_stdio`.
- **10 Compétences Spécialisées (`.agents/skills`)** :
  - `brep-kernel-architect` : Invariants d'Euler-Poincaré, carreaux de Coons, intersection surface-surface.
  - `cad-studio-engineer` : Architecture globale, solveur d'assemblage, compilation et packaging.
  - `fea-multiphysics-architect` : Synthèse de decks CalculiX CCX, maillage Tet10, validation des conditions aux limites.
  - `industrial-cam-engineer` : Cinématique RTCP 5-axes, post-processeurs CNC, détection de collisions outil/matière.
  - `loopcraft-harness-engineer` : Boucles d'auto-guérison autonomes avec classification des erreurs.
  - `neurosymbolic-cad-copilot` : Synthèse de scripts paramétriques sécurisés avec bac à sable AST.
  - `spec-driven-cad-architect` : Spécifications formelles et matrices d'invariants.
  - `techdraw-drafting-engineer` : Dessins techniques ISO 128, suppression des lignes cachées (HLR), GD&T.
  - `test-time-program-synthesizer` : Raffinement itératif de programmes géométriques avec oracles de vérification.
  - `zero-alloc-systems-craftsman` : Partage de tampons NumPy contigus en mémoire C, streaming VBO/VAO OpenGL.
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
# Création de l'environnement virtuel avec uv ou python standard
uv venv
# Ou : python -m venv .venv

# Activation :
# Sur Windows (PowerShell) :
.\.venv\Scripts\Activate.ps1
# Sur Linux / macOS :
source .venv/bin/activate
```

### 3. Installation du Package
```bash
# Installation en mode éditable avec dépendances de développement
uv pip install -e ".[dev]"
# Ou : pip install -e ".[dev]"
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

# Ou via les lanceurs multi-plateformes :
# Windows :
launch_cad_studio.bat
# Linux / macOS :
./launch_cad_studio.sh
```

### Mode Ligne de Commande Industrielle (CLI Headless)
Idéal pour les scripts d'automatisation, la validation CI/CD et les calculs distribués :
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

# Exécuter l'audit complet des 10 compétences d'agents IA
cad-cli audit-skills --deep

# Exécuter l'audit qualité industriel officiel déterministe (ISO 25010)
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
      "cwd": "C:/Users/brand/Documents/antigravity/radiant-darwin"
    }
  }
}
```

---

## 🧪 Tests & Assurance Qualité Industrielle

Le projet dispose d'une suite exhaustive de tests unitaires, d'intégration et de résistance aux cas limites :

```bash
# Exécution de la suite complète de 864 tests en mode headless
uv run pytest tests/ -v

# Vérification du Quality Gate industriel ISO 25010
uv run python scripts/industrial_audit_engine.py --cold
```

### Métriques d'Audit Qualité :
- **Tests unitaires & intégration** : **864 / 864 passés (100% de succès)**
- **Indice Composite de Maintenabilité (ISO/IEC 25010:2023 CMI)** : **96.2 / 100 [GRADE A]**
  - *Analysabilité* : 91.5 / 100
  - *Modularité* : 100.0 / 100
  - *Testabilité* : 93.2 / 100
  - *Sécurité de typage* : 100.0 / 100
  - *Robustesse* : 100.0 / 100
- **Typage statique strict** : **100.00%** (Strictement zéro `Any`, zéro `object` sur 171 modules)
- **Complexité cognitive** : Aucune fonction n'excède le plafond de 25
- **Vulnérabilités de sécurité SAST** : 0 faille détectée
- **Dépendances cycliques (Tarjan)** : 0 cycle d'architecture
- **Tests de Mutation Déterministes** : 100.0% des mutants éliminés
- **Quality Gate SonarQube Enterprise** : **PASSED (GREEN - Conforme Industriel)**

---

## 🏛️ Arborescence du Projet

```
radiant-darwin/
├── .agents/skills/              # 10 Compétences d'Agents Spécialisés SOTA
│   ├── brep-kernel-architect/
│   ├── cad-studio-engineer/
│   ├── fea-multiphysics-architect/
│   ├── industrial-cam-engineer/
│   ├── loopcraft-harness-engineer/
│   ├── neurosymbolic-cad-copilot/
│   ├── spec-driven-cad-architect/
│   ├── techdraw-drafting-engineer/
│   ├── test-time-program-synthesizer/
│   └── zero-alloc-systems-craftsman/
├── .github/
│   └── workflows/
│       └── ci.yml               # Pipeline CI/CD GitHub Actions multi-OS
├── scripts/
│   ├── industrial_audit_engine.py # Moteur d'audit déterministe ISO 25010
│   ├── multi_domain_simulation_matrix.py # Matrice Phase 1 de 8 simulations multi-physiques
│   ├── advanced_physics_simulation_matrix_phase2.py # Matrice Phase 2 (Hamiltonien, boucles fermées...)
│   ├── large_scale_systemic_simulations_phase3.py # Grandes Simulations Systémiques & Digital Twins
│   ├── advanced_destructive_bifurcation_tests.py # Banc de stress-tests destructifs & bifurcations non-linéaires
│   ├── deep_bug_hunter.py       # Chasseur de bugs et tolérancement géométrique
│   └── multi_type_simulation_fuzzer.py # Fuzzing et stress-tests multi-physiques
├── src/
│   ├── ai/                      # Serveur MCP, pont IA, synthétiseur, auto-guérison
│   ├── assembly/                # Assemblages mécaniques et détection d'interférences
│   ├── cam/                     # FAO 2.5D, 5-axes RTCP, AFP fibre, simulateur voxel, post-processeurs
│   ├── core/                    # Moteur solide, Manifold3D, DAG, Timeline, Nexus Kernel, EGC
│   ├── drawing/                 # Dessin technique ISO 128 et export SVG
│   ├── fea/                     # Éléments finis Tet4/Tet10 von Mises, ponts CalculiX et OpenFOAM
│   ├── materials/               # Base de données de matériaux, masses et centres d'inertie
│   ├── render/                  # Studio de rendu PBR, Fresnel-Schlick, raytracer
│   ├── sheetmetal/              # Tôlerie, facteur K, développée à plat, export DXF
│   ├── solver/                  # Solveur de contraintes d'esquisse 2D (SciPy TRF & Laman)
│   ├── specialized/             # Aérodynamique CFD, BIM IFC4, ECAD thermique, robotique 6-axes
│   ├── system/                  # Worker pool multithreadé, marshaling Qt événementiel
│   ├── ui/                      # Interface Qt Dark Fusion 360, ruban, palette IA
│   ├── viewport/                # Rendu OpenGL interactif, ViewCube, gizmos, streaming VBO/VAO
│   ├── cli.py                   # Interface en ligne de commande industrielle
│   └── main.py                  # Point d'entrée principal GUI / CLI
├── tests/                       # 864 tests unitaires, d'intégration et de robustesse
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
