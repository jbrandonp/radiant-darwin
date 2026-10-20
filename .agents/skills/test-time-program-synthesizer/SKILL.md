---
name: test-time-program-synthesizer
description: >-
  Synthesize, evaluate, and iteratively refine executable programs and CAD scripts at inference time using Test-Time Compute (TTC) and algebraic verification oracles inspired by François Chollet and Andrej Karpathy. Eliminates single-shot hallucinations with evolutionary refinement loops.
---

# 🧠 Test-Time Program Synthesizer (SOTA Octobre 2026)

> **Inspirations :** François Chollet (*ARC-AGI*, *Program Synthesis via Per-Task Refinement Loops*), Andrej Karpathy (*Software 3.0*, *Evals-as-Code*)  
> **Standard :** Test-Time Compute & Symbolic Verification 2026  
> **Rôle :** Synthétiseur de code et d'arbres syntaxiques (AST) au moment de l'inférence, orchestrateur de boucles de raffinement évolutif guidées par des oracles formels et des invariants géométriques.

---

## 🎯 Déclenchement & Cas d'Usage
Active ce skill pour :
- **Génération Autonome de Scripts CAO / CAM** : Traduction de requêtes géométriques complexes en code Python déterministe validé avant toute exécution utilisateur.
- **Résolution de Problèmes Algorithmiques Complexes** : Génération de solveurs ad-hoc de contraintes, de découpes de profilés ou d'optimisations topologiques nécessitant du raisonnement au test-time (*test-time compute*).
- **Remplacement du "Single-Shot" par la Recherche Évolutive** : Abandon des générations uniques probabilistes au profit d'un échantillonnage guidé par des critères d'admissibilité stricts.
- **Vérification par Oracles Mathématiques** : Contrôle automatique que le solide généré est étanche (*watertight*), de volume strictement positif, sans auto-intersection et respectant la caractéristique d'Euler $\chi = 2$.

---

## 🔄 La Boucle de Raffinement au Test-Time (Chollet-Karpathy Loop)

```
[Requête Utilisateur] 
         │
         ▼
[1. Échantillonnage Multi-Candidats (AST)] ──> [2. Filtrage Statique & Sandbox AST]
                                                         │
                                                    (Valide)
                                                         ▼
[5. Programme Validé] ◄── (Succès) ── [3. Exécution Instrumentée & Oracles]
         ▲                                               │
         │                                            (Échec)
         │                                               ▼
         └────────── (Refined Code) ◄───────── [4. Critique & Mutation Algorithmique]
```

---

### Phase 1 : Échantillonnage Multi-Candidats
- Ne jamais parier sur un seul essai (zéro-shot) pour du code de précision.
- Générer 3 à 5 variantes algorithmiques distinctes (ex: approche constructive CSG vs approche par extrusion de profilé esquissé vs révolution B-Rep).
- Chaque candidat doit être une fonction pure prenant des paramètres explicites et renvoyant une instance géométrique typée sans `Any`.

### Phase 2 : Filtrage Statique & Sandbox AST
Avant toute exécution :
- Passer le code dans l'analyseur AST (`cad_validator.py`).
- **Règles d'Exclusion Stricte** :
  - Zéro import système interdit (`os`, `subprocess`, `sys`, `shutil`, `socket`).
  - Zéro accès aux fichiers non autorisés.
  - Plafond de complexité cognitive $\le 15$ pour le script généré.
  - Rejet immédiat de tout candidat violant la sécurité.

### Phase 3 : Vérification par Oracles Géométriques
Chaque candidat admissible est exécuté dans un environnement isolé avec des oracles de vérité terrain :
1. **Oracle d'Étanchéité (Watertight)** : `assert solid.is_watertight() is True` (aucune arête frontière orpheline).
2. **Oracle de Volume** : `assert solid.volume() > 1e-6` (pas de solide dégénéré ou de volume négatif par inversion de normales).
3. **Oracle de Boîte Englobante (AABB)** : Les coordonnées extrêmes doivent être comprises dans l'enveloppe dimensionnelle spécifiée.
4. **Oracle d'Euler-Poincaré** : $\chi = V - E + F = 2(1 - g)$ doit être respecté pour la topologie demandée.

### Phase 4 : Rétroaction Critique & Mutation Algorithmique
Si un candidat échoue à un oracle :
- Extraire la trace chiffrée exacte : *"Le volume calculé est de -12.4 mm³, indiquant des normales inversées sur la face de révolution"* ou *"L'arête #42 n'est pas connectée (non-manifold)"*.
- Injecter ce diagnostic chiffré dans le modèle pour muter chirurgicalement le candidat défaillant (inversion du winding des sommets, ajustement de tolérance).
- Itérer jusqu'à convergence vers un score d'admissibilité de 100%.

### Phase 5 : Sélection de la Solution Pareto-Optimale
Parmi les candidats ayant validé 100% des oracles :
- Sélectionner le candidat ayant la **complexité cognitive la plus faible**, le **nombre minimal d'opérations booléennes**, et la **vitesse d'exécution la plus rapide**.

---

## 🔬 Fondements Scientifiques du Test-Time Compute (TTC 2024-2026)

### 1. Lois d'Échelle au Test-Time & Recherche Arborescente MCTS
- L'augmentation du budget de calcul à l'inférence via recherche arborescente de Monte Carlo (MCTS) ou Best-of-$N$ guidé par des modèles de récompense par étape (*Process Reward Models - PRMs*) surpasse systématiquement l'augmentation de la taille des paramètres pré-entraînés.
- Utilise des oracles d'exécution géométrique comme signaux d'élagage anticipé pour tronquer les branches non admissibles dès l'étape d'esquisse sans évaluer la géométrie 3D complète.

### 2. Réparation Inductive Guidée par Contre-Exemples (CEGIS)
- *Counter-Example Guided Inductive Synthesis* : lorsqu'un programme échoue à un invariant, l'oracle isole la coordonnée ou le sous-graphe exact du contre-exemple.
- L'erreur est injectée comme contrainte symbolique additionnelle dans le tour de génération suivant, garantissant la convergence monotone vers une solution conforme.

---

## 🧰 Outils & Références d'Accompagnement
- **Harnais de Synthèse & Oracles** : [`scripts/synthesize_and_verify.py`](scripts/synthesize_and_verify.py) — exécute le filtrage AST statique sandbox et le contrôle par les 4 oracles géométriques formels.
- **Spécification Mathématique des Oracles** : [`references/oracles_specification.md`](references/oracles_specification.md) — intégration de volume par Gauss-Ostrogradski et invariance d'Euler $\chi = 2$.

---

## ⚠️ Anti-Patrons & Pièges Fréquents
1. **L'illusion du "Single-Shot" probabiliste** : Faire confiance à un script généré du premier coup sans le faire passer au crible d'oracles mathématiques formels.
2. **L'exécution de code sans isolation AST** : Lancer un `exec()` ou `eval()` sur du code généré par l'IA sans avoir validé l'AST au préalable contre les imports hostiles (`subprocess`, `os`, `socket`).
3. **Le solide à normales inversées (Volume Négatif)** : Considérer un maillage valide uniquement sur le critère de fermeture topologique, alors que ses normales sont tournées vers l'intérieur ($\text{Vol} < 0$).

---

## 🛡️ Règles d'Or
1. **L'IA Propose, l'Oracle Dispose** : Une génération n'a aucune valeur tant qu'un oracle mathématique indépendant n'a pas validé ses invariants.
2. **Élimine le "Prompt-and-Pray"** : Remplacer l'espoir par la recherche dynamique dans l'espace des programmes au moment de l'exécution.
3. **Typage Fort Obligatoire** : Le script final doit être 100% annoté avec des types stricts.
