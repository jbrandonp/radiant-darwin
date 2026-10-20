---
name: cad-studio-engineer
description: >-
  Use this skill when designing, implementing, refactoring, or debugging features in CAD Studio (radiant-darwin), computational geometry kernels (hybrid B-Rep / Manifold3D), 2D sketch constraint solvers (PlaneGCS), zero-copy assembly links, shape healing pipelines, adaptive tessellation, CAM toolpaths, FEA/CFD decks, or high-performance PySide6/OpenGL CAD viewports.
---

# 🤖 CAD Studio & Computational Geometry Architect (SOTA Octobre 2026)

> **Standard :** CAD Studio Industrial Kernel v7.0 (ISO 10303 STEP, ISO 1101 GD&T, ISO 128 Drawing)  
> **Noyau :** Architecture Hybride B-Rep Analytique / Mesh Manifold3D Exact  
> **Rôle :** Architecte Senior en géométrie algorithmique, modélisation paramétrique solide, solveurs non-linéaires et moteurs CAO industriels.

---

## 🎯 Déclenchement & Cas d'Usage
Active ce skill pour toute tâche relative à :
- **Noyau Géométrique Hybride** : Solides Manifold3D, topologie B-Rep (`NexusBRep`), arènes générationnelles (`GenerationalArena`), BRepGraph $O(1)$.
- **Surfaces Paramétriques & Courbes** : Algorithme de Cox-de Boor, carreaux de Coons, surfaces NURBS rationnelles, continuités géométriques G1/G2/G3, peigne de courbure.
- **Solveur de Contraintes 2D** : Solveur non-linéaire Levenberg-Marquardt, diagnostic algébrique de Gram-Schmidt (parité `PlaneGCS`), isolation des sur-contraintes et conflits.
- **Guérison Géométrique (Shape Healing)** : Couture de bords ouverts (`sew_mesh_boundaries`), élimination des facettes dégénérées, harmonisation des normales par BFS dual-graph, réparation STEP (parité `ShapeFix`).
- **Tessellation Adaptative** : Raffinement quadtree par flèche cordale $\delta$ et déviation angulaire $\theta$ (parité `BRepMesh_IncrementalMesh`).
- **Assemblage Zéro-Copie & Scalabilité** : Liaisons mécaniques, instances liées matricielles 4x4, instanciation GPU par lot $(N, 4, 4)$ (parité `App::Link`).
- **Mise en Plan TechDraw 2D** : Découpage sub-segmentaire HLR (Hidden Line Removal), coupes brisées, cadres GD&T ASME Y14.5 / ISO 1101.
- **Sérialisation Hybride** : Archives compressées `.cadz` avec caches géométriques binaires `.npz` (parité `.FCStd` / `.brp`).
- **Multi-Physique & FAO** : Génération de jeux de données CalculiX `.inp`, CFD OpenFOAM, cinématique RTCP 5-axes, simulation de stock volumique.

---

## 🏛️ Principes Architecturaux Inviolables

1. **Typage Statique Strict Absolu (Zero-Any Policy)** :
   - Strictement zéro `Any` et zéro `object` dans tout le code source (`src/`).
   - Utiliser des `Union`, `Optional`, génériques `TypeVar`, `Protocol` ou types concrets.
2. **Plafond de Complexité Cognitive SonarQube ($\le 25$)** :
   - Toute fonction doit respecter un score de complexité cognitive $\le 25$. Décomposer les algorithmes denses en sous-fonctions fonctionnelles pures.
3. **Dualité Cohérente Mesh CSG / B-Rep** :
   - Ne jamais modifier le maillage polygonal sans resynchroniser ou adapter la topologie B-Rep sous-jacente (`NexusBRep`).
4. **Concurrence & Thread-Safety** :
   - Les calculs géométriques lourds (TPMS, FEA, maillage volumique, tessellation) s'exécutent hors du thread UI via `WorkerPool` / `QThreadPool`.
   - Tout accès concurrent au `CADDocument` est protégé par les verrous transactionnels `read_transaction()` et `write_transaction()`.
5. **Conservation de l'Énergie & Non-Régression** :
   - Chaque modification doit préserver 100% de la suite de tests (848 tests passants).

---

## 🔬 Théorèmes Scientifiques de Résolution Géométrique 2D (CAD Journal 2024-2026)

### 1. Théorème de Laman & Rigidité Structurelle 2D
Un graphe d'esquisse paramétrique à $n$ sommets et $m$ contraintes dimensionnelles est génériquement bien contraint si et seulement si :
$$m = 2n - 3 \quad \text{et} \quad \forall V' \subseteq V, \; m(V') \le 2|V'| - 3$$
- Permet une détection immédiate en temps polynomial des degrés de liberté sans inverser la matrice jacobienne complète.

### 2. Décomposition Bipartite de Dulmage-Mendelsohn (D-M)
Partitionne le système d'équations géométriques en 3 composantes irréductibles :
1. **Sous-contrainte** : Degrés de liberté résiduels identifiés pour manipulation interactive à la souris.
2. **Bien-contrainte** : Blocs carrés réguliers résolus de manière découplée par Levenberg-Marquardt.
3. **Sur-contrainte** : Détection des équations redondantes ou contradictoires pour diagnostic visuel immédiat dans l'arbre d'esquisse.

---

## 🛠️ Composants Clés du Répertoire `src/core/`

- **Géométrie Solide & Booléens** : [`src/core/geometry.py`](src/core/geometry.py) (`Solid`, `fuzzy_union`, `fuzzy_difference`, `fuzzy_intersection`).
- **Noyau Nexus B-Rep** : [`src/core/nexus_kernel/`](src/core/nexus_kernel/) (`NexusBRep`, `NexusSolid`, `GenerationalArena`, `saye_quadrature.py`, `trimmed_brep_watertight.py`).
- **Surfaces NURBS Continues** : [`src/core/nexus_kernel/nurbs_surface.py`](src/core/nexus_kernel/nurbs_surface.py) (`NexusNURBSSurface`, `make_coons_patch`, continuités G1/G2/G3).
- **Tessellation Adaptative** : [`src/core/adaptive_tessellation.py`](src/core/adaptive_tessellation.py) (`AdaptiveTessellator`, quadtree cordal et angulaire).
- **Guérison Topologique** : [`src/core/shape_healing.py`](src/core/shape_healing.py) (`ShapeFixer`, couture, orientation, réparation STEP).
- **Solveur de Contraintes 2D** : [`src/solver/constraints_2d.py`](src/solver/constraints_2d.py) (`SketchConstraintSolver2D`, `diagnose_constraints`).
- **Assemblage & Zéro-Copie** : [`src/core/assembly.py`](src/core/assembly.py) (`AssemblyLink`, `AssemblyLinkManager`, `AssemblySolver`).
- **Grandeurs Physiques & Unités** : [`src/core/units.py`](src/core/units.py) (`PhysicalQuantity` avec algèbre $[M, L, T]$).
- **Sérialisation & Caches Binaires** : [`src/core/serializer.py`](src/core/serializer.py) (`ProjectSerializer`, caches `.npz`).
- **Moteur de Dessin 2D TechDraw** : [`src/drawing/drawing_generator.py`](src/drawing/drawing_generator.py) (HLR sub-segmentaire, GD&T, coupes).

---

## 🧰 Outils & Références d'Accompagnement
- **Vérificateur Topologique Déterministe** : [`scripts/verify_mesh_manifold.py`](scripts/verify_mesh_manifold.py) — contrôle l'étanchéité, l'absence d'arêtes non-variétales et l'invariant d'Euler $\chi = 2$.
- **Guide d'Intégration PySide6 / Manifold3D** : [`references/manifold3d_pyside6_patterns.md`](references/manifold3d_pyside6_patterns.md) — patrons de thread-worker typés sans `object` et VBO OpenGL.

---

## ⚠️ Anti-Patrons & Pièges Fréquents
1. **L'illusion du Minkowski global sur congé (Fillet)** : Ne jamais appliquer une somme de Minkowski sphérique globale qui altère toutes les dimensions du solide pour arrondir une seule arête sélectionnée.
2. **L'oubli de la garde epsilon sur les normales de coupe** : Toujours diviser par `max(norm_proj, 1e-12)` pour prévenir toute exception `ZeroDivisionError` sur les facettes effilées (*slivers*).
3. **Le piège du STEP "STL Déguisé" (`FACETED_BREP`)** : Ne pas sérialiser les triangles du maillage avec des surfaces nulles `$`. Préférer les surfaces analytiques (`PLANE`, `CYLINDRICAL_SURFACE`) compatibles SolidWorks/Mastercam.
4. **La désynchronisation Mesh CSG / B-Rep** : Toute opération booléenne sur le maillage Manifold3D doit répercuter le graphe topologique des arêtes et faces dans `NexusBRep`.

---

## 📋 Protocole d'Exécution en 5 Étapes

### Étape 1 : Cartographie d'Invariants & Spécification Préalable (Spec-First)
- Définir mathématiquement les invariants géométriques avant tout code (volume $> 0$, caractéristique d'Euler $\chi = 2(1-g)$, tolérance de tangence).
- Vérifier si l'opération implique une discontinuité flottante IEEE 754 et définir la tolérance de clustering spatial.

### Étape 2 : Implémentation Algorithmique Découplée
- Isoler les fonctions d'évaluation pure des structures d'état.
- Pour les boucles de calcul (quadtree, maillage, BFS), extraire les structures auxiliaires (`DisjointSet`, `SpatialGrid`) pour garder la complexité cognitive $\le 15$.

### Étape 3 : Validation Déterministe & Non-Régression
- Exécuter la suite de tests ciblée :
  ```bash
  .venv\Scripts\python.exe -m pytest tests/test_votre_module.py
  ```
- Vérifier le typage statique strict :
  ```bash
  .venv\Scripts\python.exe scripts/strict_typing_visitor.py src/core/votre_module.py
  ```

### Étape 4 : Passage du Quality Gate Industriel
- Exécuter le moteur d'audit unifié :
  ```bash
  .venv\Scripts\python.exe scripts/industrial_audit_engine.py
  ```
- Vérifier les 5 critères :
  1. Typage statique : 100.00% (zéro `Any`, zéro `object`)
  2. Sécurité SAST : 0 violation
  3. Dépendances circulaires (Tarjan) : 0 cycle
  4. Complexité cognitive : 0 fonction $> 25$
  5. Score de mutation déterministe : $\ge 80\%$

### Étape 5 : Traçabilité Eager Logging & Git
- Noter l'opération dans le journal Obsidian actif (`Gemini_Logs/Projects/_Active/`).
- Créer un commit Conventional Commits en anglais : `type(scope): description`.
- Créer le tag d'audit `audit-vN` correspondant et pousser sur GitHub.
