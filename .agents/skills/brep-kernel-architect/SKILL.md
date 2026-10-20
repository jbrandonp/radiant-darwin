---
name: brep-kernel-architect
description: >-
  Use this skill when designing, implementing, or debugging Exact Boundary Representation (B-Rep) topological data structures, Euler-Poincaré invariants (V - E + F = 2(1 - g)), half-edge / BRepGraph adjacency queries, Cox-de Boor NURBS curves and surfaces, Coons patches, Surface-Surface Intersection (SSI) solvers, or topological sewing and healing.
---

# 📐 B-Rep & Computational Geometry Kernel Architect (SOTA Octobre 2026)

> **Inspirations :** OpenCASCADE Technology (OCCT 8.0 BRepGraph), Siemens Parasolid, Spatial ACIS, Emmett Lalish (Manifold3D)  
> **Standard :** ISO 10303 STEP AP242 / ISO 1101 Continuous Boundary Representation  
> **Rôle :** Spécialiste de la topologie de frontière exacte, des variétés 2D/3D, des surfaces paramétriques rationnelles et des solveurs d'intersection géométrique.

---

## 🎯 Déclenchement & Cas d'Usage
Active ce skill pour :
- **Topologie B-Rep Exacte** : Manipulation des structures hiérarchiques (Vertex, Edge, Wire, Face, Shell, Solid).
- **Invariants Topologiques d'Euler-Poincaré** : Vérification stricte de la caractéristique d'Euler $\chi = V - E + F = 2(1 - g)$ et de l'orientabilité 2-variété.
- **BRepGraph & Adjacence $O(1)$** : Indexation par arènes générationnelles (`GenerationalArena`) et tables plates de demi-arêtes (Half-Edges) pour éliminer les parcours récursifs lents.
- **Surfaces Paramétriques NURBS & B-Splines** : Algorithme récursif de Cox-de Boor, carreaux de Coons bilinéaires/bicubiques, calcul exact des formes fondamentales ($E, F, G, L, M, N$) et des courbures gaussienne/moyenne ($K, H$).
- **Intersection Surface-Surface (SSI)** : Résolution analytique (Plan-Plan, Plan-Cylindre, Plan-Sphère) et traçage numérique Marching Newton-Raphson avec pas adaptatif.
- **Guérison Géométrique & Tolérancement Flou** : Couture de fissures IEEE 754, snapping spatial cubique en $O(N)$, et harmonisation de normales par parcours de graphe dual.

---

## 🏛️ Invariants Mathématiques & Topologiques Majeurs

### 1. Théorème d'Euler-Poincaré pour les Solides Polyédriques
Pour tout solide étanche fermé de genre $g$ (nombre de trous traversants) :
$$\chi = V - E + F = 2(1 - g)$$
- Si le solide possède des anneaux intérieurs (Inner Wires / Trous dans les faces, $H$) :
$$V - E + F - H = 2(1 - g)$$
- Tout composant retournant $\chi \ne 2(1 - g)$ est **non-variétal (non-manifold)** ou fissuré.

### 2. Continuités Géométriques de Raccordement (Classe A)
- **$G^0$ (Continuité de position)** : Les courbes frontières coïncident spatialement ($\|S_a(u, 1) - S_b(u, 0)\| \le \varepsilon_{pos}$).
- **$G^1$ (Continuité tangentielle)** : Les vecteurs normaux unitaires sont colinéaires ($\arccos(N_a \cdot N_b) \le \varepsilon_{ang}$).
- **$G^2$ (Continuité de courbure)** : Les rayons de courbure principaux sont identiques ($\Delta\kappa \le \varepsilon_{curv}$). Élimine les reflets cassés sur les carrosseries automobiles et pièces optiques.
- **$G^3$ (Continuité du jerk géométrique)** : La dérivée de la courbure est continue (raccordements aérodynamiques sans turbulence induite).

### 3. Demi-Arêtes & Orientabilité (Half-Edge Structure)
- Chaque arête topologique $E$ est dédoublée en deux demi-arêtes dirigées opposées : $h$ et $\text{twin}(h)$.
- Dans un maillage manifold fermé :
  $$\text{twin}(\text{twin}(h)) = h$$
- Deux faces adjacentes traversant la même arête $E$ doivent obligatoirement parcourir l'arête en sens inverse pour garantir des normales extérieures cohérentes.

### 4. Paradigmes Scientifiques Récents de B-Rep IA (SIGGRAPH 2024 / Autodesk)
- **SolidGen (IBR - Indexed B-Rep)** : Synthèse autorégressive séquentielle d'entités topologiques ($V \to E \to F$) garantissant la validité par masquage d'attention causal.
- **BrepGen (SIGGRAPH 2024)** : Représentation arborescente hiérarchique de géométrie latente diffusée de haut en bas, avec fusion de nœuds dupliqués pour reconstituer la topologie B-Rep étanche sans approximation polygonale.
- **DualBrep (Flow Matching Continu)** : Formulation dans le domaine euclidien continu unifiant le champ de distance signée (SDF pour la forme globale) et le champ de distance non signée de Voronoi (UDF pour les éléments de surface) avec reconstruction neuronale étanche.

### 5. Intersection Surface-Surface Certifiée (SSI & Opérateur de Krawczyk 2024-2026)
- **Certification Topologique par Intervalles** : Résolution du système non-linéaire $F(u_1, v_1, u_2, v_2) = S_1(u_1, v_1) - S_2(u_2, v_2) = 0$.
- **Opérateur de Krawczyk $K(X)$** :
  $$K(X) = m(X) - Y \cdot F(m(X)) + (I - Y \cdot F'(X))(X - m(X))$$
  Si $K(X) \subset \text{int}(X)$, prouve mathématiquement l'existence et l'unicité d'une branche de courbe d'intersection dans la boîte paramétrique 4D $X$, éliminant les boucles orphelines et les fausses intersections.
- **Isolation des Singularités** : Détecte et isole les points de tangence rasante et cusps où $\mathrm{rank}(F') < 3$, garantissant la fermeture des coques découpées sans divergence.

---

## 🛠️ Boîte à Outils Algorithmique

### 1. Recherche d'Intervalle de Nœuds NURBS (Algorithm A2.1 Piegl & Tiller)
Pour évaluer une B-Spline de degré $p$ au paramètre $u$, trouver l'intervalle $i$ tel que $u_i \le u < u_{i+1}$ via recherche dichotomique $O(\log N)$ :
```python
def find_knot_span(n: int, p: int, u: float, knots: np.ndarray) -> int:
    if u >= knots[n + 1]:
        return n
    if u <= knots[p]:
        return p
    low = p
    high = n + 1
    mid = (low + high) // 2
    while u < knots[mid] or u >= knots[mid + 1]:
        if u < knots[mid]:
            high = mid
        else:
            low = mid
        mid = (low + high) // 2
    return mid
```

### 2. Solveur SSI Newton-Raphson avec Pas de Marche Adaptatif
Pour trouver l'intersection entre deux surfaces implicites ou paramétriques $S_1(u_1, v_1) = S_2(u_2, v_2)$ :
1. Calculer le vecteur tangent de marche $T = N_1 \times N_2$.
2. Avancer d'un pas adaptatif $h = \min(h_{max}, \frac{\delta_{chord}}{\kappa_{max}})$.
3. Projeter par correction orthogonale de Newton-Raphson sur les deux surfaces simultanément.

---

## 🧰 Outils & Références d'Accompagnement
- **Vérificateur d'Invariants B-Rep** : [`scripts/verify_brep_invariants.py`](scripts/verify_brep_invariants.py) — vérifie la réciprocité des demi-arêtes jumelles (`e.twin.twin == e`), la fermeture cyclique des boucles de face et la caractéristique d'Euler.
- **Guide Topologique BRepGraph** : [`references/brep_graph_topology.md`](references/brep_graph_topology.md) — relations de connectivité, demi-arêtes et formule généralisée $V - E + F - (L - F) = 2(S - G)$.

---

## ⚠️ Anti-Patrons & Pièges Fréquents
1. **L'arête "Papillon" (Non-Manifold Edge)** : Une arête topologique partagée par 3 faces ou plus détruit l'orientabilité et fait échouer les opérations booléennes.
2. **La singularité polaire des quadriques** : Aux pôles d'une sphère ou d'un cône, la dérivée partielle s'annule ($\partial S / \partial u = 0$). Remplacer l'évaluation cartésienne naïve par des carreaux de Coons ou un découpage polaire adapté.
3. **Le pas fixe en intersection de surfaces (SSI)** : Un pas de marche constant saute par-dessus les petites boucles d'intersection fermées. Le pas doit obligatoirement s'adapter à la courbure $h \propto 1/\kappa$.

---

## 📋 Checklist de Validation B-Rep

- [ ] L'enveloppe extérieure forme un `CLOSED_SHELL` étanche (0 arête frontière ouverte).
- [ ] Aucune arête n'est partagée par 3 faces ou plus (singularité non-manifold).
- [ ] Aucun triangle ou face n'a une aire inférieure à $10^{-9}$ mm² (facette écrasée).
- [ ] Les normales de toutes les faces pointent strictement vers l'extérieur du volume matière.
- [ ] En cas d'export STEP, toutes les surfaces quadriques et planes sont typées analytiquement (`ADVANCED_BREP_SHAPE_REPRESENTATION`).
