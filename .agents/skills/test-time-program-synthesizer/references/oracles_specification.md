# Spécification Mathématique des Oracles de Vérification CAO (SOTA 2026)

Inspiré des travaux de François Chollet (ARC-AGI-2/3) et Andrej Karpathy (Software 3.0), ce document formalise les critères d'acceptation mathématiques pour tout programme CAO généré au moment du test (*Test-Time Compute*).

---

## Les 4 Oracles Géométriques Incontournables

```
                ┌──────────────────────────────────────┐
                │   Programme Candidat AST Généré      │
                └──────────────────┬───────────────────┘
                                   │
                                   ▼
        ┌──────────────────────────────────────────────────────┐
        │ 1. Oracle d'Étanchéité (Watertight Manifold)         │
        ├──────────────────────────────────────────────────────┤
        │ 2. Oracle de Volume Positif (Divergence Theorem)     │
        ├──────────────────────────────────────────────────────┤
        │ 3. Oracle d'Euler-Poincaré (V - E + F = 2(1 - g))    │
        ├──────────────────────────────────────────────────────┤
        │ 4. Oracle de Bornage Dimensionnel (AABB Invariant)   │
        └──────────────────────────────────────────────────────┘
```

---

### 1. Oracle d'Étanchéité (*Watertight Manifold*)
Un solide CAO valide ne peut comporter ni bord ouvert ni arête non-variétale :
- **Condition de 2-Variété Pure** : Chaque arête non orientée $e = \{u, v\}$ doit être partagée par **exactement 2 faces adjacentes**.
- **Cohérence d'Orientation (Winding)** : Si la face $F_1$ parcourt l'arête dans le sens $(u \to v)$, la face adjacente $F_2$ doit impérativement la parcourir dans le sens opposé $(v \to u)$.
- **Sanction en cas d'échec** : Rejet immédiat avec signalisation des indices d'arêtes frontières.

### 2. Oracle de Volume Positif (*Divergence Theorem*)
Le volume du solide est calculé de manière exacte par intégration de surface selon le théorème de Gauss-Ostrogradski :
$$\text{Vol}(\Omega) = \frac{1}{6} \sum_{i=1}^{N_{\text{faces}}} \mathbf{v}_{i,0} \cdot (\mathbf{v}_{i,1} \times \mathbf{v}_{i,2})$$
- Si $\text{Vol} \le 0$, les normales de surface sont inversées ou le solide est dégénéré.
- **Seuil d'Admissibilité** : $\text{Vol} > 10^{-6}\text{ mm}^3$.

### 3. Oracle d'Euler-Poincaré
Pour tout polyèdre ou maillage orientable sans auto-intersection de genre $g$ (où $g$ est le nombre de trous traversants) :
$$\chi = V - E + F = 2(1 - g)$$
- Pour un solide standard sans trou ($g=0$) : $\chi = 2$.
- Pour un solide toroïdal avec 1 trou ($g=1$) : $\chi = 0$.
- Toute divergence indique des sommets orphelins, des faces dupliquées ou des trous topologiques microscopiques.

### 4. Oracle de Bornage Dimensionnel (*AABB Containment*)
Le solide doit respecter l'enveloppe machine ou le volume d'assemblage défini dans la spécification :
$$\forall \mathbf{p} \in \text{Vertices}, \quad \mathbf{p}_{\min} \le \mathbf{p} \le \mathbf{p}_{\max}$$
- Empêche les singularités numériques projetant des sommets à l'infini ($\pm \infty$ ou `NaN`).
