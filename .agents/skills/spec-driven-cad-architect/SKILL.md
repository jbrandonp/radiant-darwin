---
name: spec-driven-cad-architect
description: >-
  Use this skill when authoring mathematical specifications, engineering contracts, invariant matrices, pre-conditions, post-conditions, and characterization test suites before implementing complex CAD, CAM, or geometric algorithms. Eliminates 'vibe coding' regressions and cognitive debt.
---

# 📜 Spec-Driven CAD Architect & Invariant Designer (SOTA Octobre 2026)

> **Inspirations :** Andrej Karpathy (Spec-First Engineering vs Vibe Coding), Martin Fowler (Characterization Testing), Barbara Liskov (Liskov Substitution & Behavioral Subtyping)  
> **Standard :** Formal Verification & Contract-Driven Computational Engineering 2026  
> **Rôle :** Concepteur de spécifications formelles, d'invariants topologiques stricts et de contrats logiciels préalables pour systèmes CAO/FAO critiques.

---

## 🎯 Déclenchement & Cas d'Usage
Active ce skill pour :
- **Conception de Nouvelles Fonctionnalités CAO** : Avant d'écrire la moindre ligne de code d'implémentation pour une extrusion, un congé, une poche, une répétition ou une liaison cinématique.
- **Élimination du "Vibe Coding"** : Remplacement des prompts vagues et des essais-erreurs par des contrats mathématiques formels et univoques.
- **Tests de Caractérisation & Invariants** : Écriture préalable des tests de non-régression et des bornes géométriques (blast-radius).
- **Prévention de la Dette Cognitive** : Conservation de modèles mentaux clairs des structures sous-jacentes (Euler, géométrie rationnelle, allocation mémoire).

---

## 📐 Les 4 Quadrants d'une Spécification CAO Industrielle

Toute nouvelle fonctionnalité ou refactorisation doit être spécifiée selon cette grille avant implémentation :

```
┌──────────────────────────────────────┬──────────────────────────────────────┐
│  QUADRANT 1 : CONTRAT GÉOMÉTRIQUE    │  QUADRANT 2 : INVARIANTS TOPOLOGIQUES│
│  - Domaine paramétrique valide       │  - Euler-Poincaré : V - E + F = 2    │
│  - Unités physiques & dimensions     │  - Étanchéité (0 arête frontière)    │
│  - Singularités mathématiques        │  - Volume > 0 (normales sortantes)   │
├──────────────────────────────────────┼──────────────────────────────────────┤
│  QUADRANT 3 : COMPORTEMENT AUX BORNES│  QUADRANT 4 : MATRICE DE TESTS       │
│  - Micro-interstices IEEE 754        │  - Cas nominaux standards            │
│  - Dégénérescence (R -> 0, L -> inf) │  - Cas limites (Zero/Infinity)       │
│  - Gestion d'exceptions typées       │  - Symétrie transactionnelle (Undo)  │
└──────────────────────────────────────┴──────────────────────────────────────┘
```

---

## 📝 Modèle de Spécification Formelle (CAD Feature Spec Template)

```markdown
# SPÉCIFICATION TECHNIQUE : [Nom de la Fonctionnalité / Feature]

### 1. Domaine Paramétrique & Types d'Entrée
- Paramètre $P_1$ : $[min, max] \subset \mathbb{R}$, Unité : [mm, deg, N, etc.]
- Pré-condition : $P_1 > 0$ et $P_2 \le \text{Rayon\_Max}$
- Exceptions typées levées : `ValueError` si $P_1 \le 0$, `TopologyError` si auto-intersection.

### 2. Invariants Topologiques Obligatoires
- Invariant 1 (Variété 2-Manifold) : Chaque arête du solide résultat est partagée par exactement 2 faces.
- Invariant 2 (Conservation du Genre) : Si l'opération ne perce pas la pièce, $\Delta g = 0$.
- Invariant 3 (Volume Positif) : $\text{Volume}(S_{post}) > 0.0$ et orientation normale extérieure.

### 3. Matrice de Tests Déterministes (Écrite AVANT le code)
1. **Test Nominal** : Entrées standards vérifiant la géométrie exacte attendue.
2. **Test aux Limites (Boundary)** : Paramètre au seuil minimum ($P = \varepsilon = 10^{-4}$).
3. **Test d'Incompatibilité Dimensionnelle** : Addition ou opération avec grandeur physique erronée.
4. **Test de Réversibilité Transactionnelle** : `undo()` ramène le document au hash exact d'origine.
5. **Test de Performance / Complexité** : Temps d'exécution $< 50$ ms sur un maillage de 5 000 facettes.
```

---

## 🔬 Fondements Scientifiques du Calcul Géométrique Exact (EGC 2024-2026)

### 1. Séparation Décision Combinatoire vs Construction Géométrique
- En géométrie computationnelle moderne, les décisions combinatoires (prédicats topologiques : point intérieur/extérieur, orientation 3D) doivent être résolues avec une exactitude absolue, tandis que les constructions (coordonnées des points d'intersection) admettent une approximation d'intervalle contrôlée.
- Cette distinction prévient les effondrements de topologie (bords ouverts, facettes non-manifold) dus aux approximations flottantes IEEE 754.

### 2. Prédicats Adaptatifs Multi-Niveaux de Shewchuk
- **Niveau 1 (Fast Path Flottant)** : Évaluation rapide en double précision standard avec borne d'erreur statique $\varepsilon$. Si $|\det(\mathbf{A})| > \varepsilon$, le signe est mathématiquement certain et la fonction retourne immédiatement ($>99\%$ des requêtes).
- **Niveau 2 (Filtre d'Intervalles Dynamique)** : Encadrement par arithmétique d'intervalles $[a, b]$ si le déterminant approche de zéro.
- **Niveau 3 (Arithmétique d'Expansion Exacte)** : Calcul sur sommes non évaluées de flottants pour déterminer le signe exact sans basculer sur des bibliothèques multiprécision lentes.

---

## 🧰 Outils & Références d'Accompagnement
- **Auditeur de Spécifications Formelles** : [`scripts/audit_feature_contract.py`](scripts/audit_feature_contract.py) — vérifie la complétude des 4 quadrants dans les documents de spécification.
- **Modèle de Spécification Formelle** : [`templates/cad_spec_contract_template.md`](templates/cad_spec_contract_template.md) — gabarit contractuel standardisé pour définir les invariants, gardes et tests.

---

## 🚫 Anti-Patterns à Proscrire Impérativement

1. **Le "Vibe Coding" à l'Aveugle** : Générer 200 lignes de code Python en espérant que ça fonctionne sans avoir défini les équations mathématiques de la transformation.
2. **Le Masquage Silencieux d'Erreurs (`except: pass`)** : Remplacer silencieusement une géométrie échouée par un cube ou une forme par défaut sans avertir l'utilisateur ni lever d'exception.
3. **L'Usage de Types Flous (`Any`, `object`)** : Affaiblir la vérification statique pour faire passer le linter. Tout type doit être modélisé précisément.
4. **La Prolifération Cognitive** : Écrire des fonctions géantes à 10 niveaux d'indentation imbriqués ($CC > 25$). Découper systématiquement en fonctions fonctionnelles pures.
