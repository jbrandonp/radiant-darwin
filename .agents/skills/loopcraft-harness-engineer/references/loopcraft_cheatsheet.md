# Antisèche Opérationnelle Loopcraft (SOTA Octobre 2026)

Ce guide rapide résume les commandes et les réflexes pour mener à bien des boucles d'auto-guérison et de développement autonome.

---

## 1. La Taxonomie des 5 Erreurs
Quand un test ou une commande échoue, l'agent doit classer l'anomalie en moins de 5 secondes :
1. **`SYNTAX`** : AST non analysable, parenthèse ou crochet non fermé.
2. **`RUNTIME`** : Exception Python pendant l'exécution (`AttributeError`, `IndexError`, `ZeroDivisionError`).
3. **`TEST_FAIL`** : L'assertion logique du test renvoie faux (`assert res == expected`).
4. **`LINT`** : Violation de typage strict (`Any`/`object`) ou complexité cognitive $> 25$.
5. **`SECURITY`** : Injection de chemin (*path traversal*), lecture illimitée de fichier, division par zéro non gardée.

---

## 2. Commandes d'Isolation Git Worktree (Multiplexage d'Agents)
Pour lancer une tâche lourde sans perturber la branche principale de travail :
```bash
# 1. Créer une branche et un espace de travail dédié
git worktree add ../radiant-feature-branch -b feat/my-subsystem

# 2. Revenir ou supprimer l'arbre une fois fusionné
git worktree remove ../radiant-feature-branch
```

---

## 3. Déroulement Déterministe d'un Patch
```
[Observer Erreur] ──> [Poser Invariant] ──> [Appliquer Diff Minimal] ──> [Exécuter Harnais]
```
- Ne jamais réécrire tout un module.
- Si une fonction approche une complexité cognitive de 20, extraire un sous-helper pur.
- Chaque cycle résolu est immédiatement verrouillé par un commit `fix(scope): description`.
