---
name: fea-multiphysics-architect
description: >-
  Architect and implement Finite Element Analysis (FEA) and Computational Fluid Dynamics (CFD) pipelines, Gmsh tetrahedral meshing (Tet4/Tet10), CalculiX CCX deck synthesis, boundary condition validation, and OpenFOAM Navier-Stokes simulations.
---

# 🔬 FEA & Multi-Physics Simulation Architect (SOTA 2026)

> **Solveurs :** CalculiX CCX (Structure/Thermique), Gmsh (Maillage Volumique), OpenFOAM (CFD Écoulement)  
> **Standard :** ISO 16730 Évaluation des modèles de calcul, NAFEMS Benchmarks  
> **Rôle :** Spécialiste du calcul de structures par éléments finis, du maillage tétraédrique, des conditions aux limites et de la mécanique des milieux continus.

---

## 🎯 Déclenchement & Cas d'Usage
Active ce skill pour toute tâche relative à :
- **Maillage Volumique Gmsh** : Génération d'éléments tétraédriques linéaires (Tet4) et quadratiques (Tet10), contrôle du rapport d'aspect (*aspect ratio*) et de la dégénérescence d'angles solides.
- **Résolution Statique Linéaire & Non-Linéaire** : Assemblage de la matrice de rigidité globale $\mathbf{K} \cdot \mathbf{U} = \mathbf{F}$ via solveurs creux directs (SciPy `spsolve`, Pardiso, Spooles).
- **Jeux de Données CalculiX (`.inp`)** : Synthèse de decks de calcul (`*NODE`, `*ELEMENT`, `*MATERIAL`, `*STEP`, `*BOUNDARY`, `*CLOAD`, `*NODE FILE`) et parsing des résultats `.frd`.
- **Analyse des Contraintes de Von Mises & Déformations** : Calcul des contraintes principales, critère de plasticité de von Mises et tenseurs de déformations de Green-Lagrange.
- **Simulation d'Écoulement CFD OpenFOAM** : Définition des dossiers `0/`, `constant/`, `system/`, maillage `snappyHexMesh`, et résolution stationnaire `simpleFoam`.

---

## 🏛️ Invariants Mathématiques de la Simulation Numérique

### 1. Assemblage de Rigidité & Conditionnement
$$\mathbf{K} = \sum_{e=1}^{N_e} \mathbf{L}_e^T \mathbf{K}_e \mathbf{L}_e, \quad \mathbf{K} \mathbf{U} = \mathbf{F}$$
- **Règle d'Or de Non-Singularité** : Pour éviter tout mouvement de corps rigide ($\det(\mathbf{K}) = 0$), le modèle doit impérativement bloquer au minimum **6 degrés de liberté** dans l'espace 3D (3 translations + 3 rotations).

### 2. Contrainte Équivalente de Von Mises
$$\sigma_{\text{vM}} = \sqrt{\frac{1}{2}\left[(\sigma_{xx} - \sigma_{yy})^2 + (\sigma_{yy} - \sigma_{zz})^2 + (\sigma_{zz} - \sigma_{xx})^2 + 6(\sigma_{xy}^2 + \sigma_{yz}^2 + \sigma_{zx}^2)\right]}$$
- Comparée à la limite d'élasticité du matériau $R_e$ pour obtenir le coefficient de sécurité minimal :
$$s = \frac{R_e}{\max(\sigma_{\text{vM}})}$$

---

## 🧰 Outils & Références d'Accompagnement
- **Vérificateur de Deck CalculiX / FEA** : [`scripts/verify_fea_deck.py`](scripts/verify_fea_deck.py) — contrôle les degrés de liberté bloqués, vérifie les propriétés élastiques ($E, \nu$) et calcule la qualité de maillage.
- **Guide des Mots-Clés CalculiX & CFD** : [`references/fea_boundary_conditions.md`](references/fea_boundary_conditions.md) — syntaxe des cartes `.inp`, types d'éléments `C3D10` et modèles de turbulence OpenFOAM $k$-$\varepsilon$.

---

## ⚠️ Anti-Patrons & Pièges Fréquents
1. **Le mouvement de corps rigide (Rigid Body Motion)** : Oublier de brider un axe de rotation ou de translation, conduisant à une matrice singulière non inversable.
2. **L'élément plat ou aiguille (High Aspect Ratio Sliver)** : Des tétraèdres dont le rapport longueur/hauteur dépasse 50 faussent dramatiquement les gradients de contraintes locaux.
3. **Le coefficient de Poisson incompressible ($\nu \to 0.5$)** : Un matériau avec $\nu \ge 0.499$ provoque un blocage volumétrique numérique (*volumetric locking*) sur les éléments linéaires Tet4. Toujours privilégier Tet10.
