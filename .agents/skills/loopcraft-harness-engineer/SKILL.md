---
name: loopcraft-harness-engineer
description: >-
  Use this skill when designing, setting up, or executing autonomous agentic loops, self-healing test harnesses, continuous verification pipelines, automated error classification (SYNTAX, RUNTIME, TEST_FAIL, LINT, SECURITY), or SonarQube / ISO 25010 Quality Gates. Enforces systematic plan-code-test-diagnose cycles with up to 8 bounded iterations.
---

# 🔁 Loopcraft & Self-Healing Harness Engineer (SOTA Octobre 2026)

> **Inspirations :** Boris Cherny (créateur de *Claude Code* chez Anthropic), Peter Steinberger (*OpenClaw*, OpenAI), Addy Osmani (*Loop Engineering* & *Own the Outer Loop*), Simon Willison (*Progressive Skills & Evals*), Mitchell Hashimoto (*Deterministic State Transitions*)  
> **Axiome Fondateur (Cherny & Steinberger) :** *"You shouldn't be prompting coding agents anymore. You should be designing loops that prompt your agents. Prompts burn, skills compound."*  
> **Standard :** Agentic Engineering Framework 2026  
> **Rôle :** Architecte des boucles de feedback autonomes, des harnais de tests auto-réparateurs et de la gouvernance de code par rétroaction déterministe.

---

## 🎯 Déclenchement & Cas d'Usage
Active ce skill pour :
- **Boucles d'auto-guérison (Self-Healing Loops)** : Résolution autonome de bugs, régression de tests, ou dette technique complexe sans supervision humaine constante (jusqu'à 8 itérations bornées).
- **Architecture de Boucle Interne vs Boucle Externe (Inner vs Outer Loop)** : L'agent pilote la boucle interne (plan -> code -> test -> diagnostic -> fix), tandis que le développeur pilote la boucle externe (objectifs, Quality Gates ISO 25010, score CMI, goût architectural).
- **Multiplexage & Essaims d'Agents Parallèles** : Découplage des tâches de refactorisation ou d'investigation via des environnements de travail étanches (`git worktree`) sans conflit d'écriture.
- **Harnais d'Évaluation & Evals Déterministes** : Mise en place de suites d'évaluation programmatiques fournissant un signal clair (binaire ou quantifié) à l'agent.
- **Gouvernance de Quality Gate** : Respect strict des 5 piliers ISO/IEC 25010 (Analysabilité, Modularité, Testabilité, Typage, Robustesse) et du plafond SonarQube de complexité cognitive ($\le 25$).
- **Classification Automatique des Erreurs** : Analyse systématique de `stdout`/`stderr` et routage précis vers la cause racine sans tâtonnement aléatoire.

---

## 🔄 Le Cycle d'Exécution en 5 Étapes (Loopcraft Lifecycle)

```
[1. OBSERVE & CLASSIFY] ──> [2. SPEC & BLAST-RADIUS] ──> [3. EXECUTE MINIMAL DIFF]
         ▲                                                               │
         │                                                               ▼
[5. AUDIT & LOG] <── (Pass) ── [4. HARNESS VERIFICATION] ◄───────────────┘
                                        │
                                     (Fail)
                                        │
                         (Up to 8 bounded iterations)
```

### Étape 1 : Observation & Classification d'Erreur
Classifier immédiatement le problème dans l'une des 5 catégories :
1. `SYNTAX` : Erreur de compilation ou d'analyse AST.
2. `RUNTIME` : Exception levée lors de l'exécution (`AttributeError`, `KeyError`, `IndexError`, etc.).
3. `TEST_FAIL` : Échec d'assertion fonctionnelle ou régression dans la suite de tests.
4. `LINT` : Violation de style, complexité cognitive $> 25$, ou violation de typage (`Any`/`object`).
5. `SECURITY` : Vulnérabilité SAST, injection de chemin, secret ou clé non masquée.

### Étape 2 : Spécification d'Invariant & Rayon d'Impact (Blast-Radius)
- **Avant d'écrire une ligne de code**, définir l'invariant brisé.
- Évaluer le rayon d'impact : quels modules appellent cette fonction ? Quelles structures de données sont partagées ?
- Formuler l'hypothèse de correction en une phrase claire.

### Étape 3 : Application du Diff Minimal (Smallest Sufficient Patch)
- Éviter le "churn" volumétrique : ne pas réécrire un fichier entier si une retouche chirurgicale de 5 lignes suffit.
- Préserver tous les commentaires et docstrings existants.
- Garantir un typage 100% strict (refuser d'utiliser `Any` ou `object`).
- Si une fonction approche la complexité cognitive de 20, extraire un sous-helper pur.

### Étape 4 : Vérification par Harnais Déterministe
Exécuter la vérification en cascade :
```bash
# 1. Test unitaire ciblé
.venv\Scripts\python.exe -m pytest tests/test_cible.py

# 2. Audit de typage strict (zéro Any)
.venv\Scripts\python.exe scripts/strict_typing_visitor.py

# 3. Audit de complexité cognitive (CC <= 25)
.venv\Scripts\python.exe scripts/codescene_analyzer.py

# 4. Audit de sécurité SAST
.venv\Scripts\python.exe scripts/security_sast_visitor.py
```
- **Si échec** : Analyser le message d'erreur exact, déterminer pourquoi l'hypothèse a échoué (backtracking explicite), et itérer (jusqu'à **8 itérations maximum** avant d'appeler l'utilisateur à l'aide).
- **Si succès** : Passer à l'étape 5.

### Étape 5 : Journalisation Eager & Verrouillage Git
- Mettre à jour la note Obsidian active avec le rapport de résolution :
  - Cause racine
  - Solution appliquée
  - Métriques d'audit
- Créer un commit Conventional Commits : `fix(scope): description` ou `feat(scope): description`.
- Créer le tag git d'audit correspondant `audit-vN`.

---

## 🔬 Fondements Scientifiques de l'Auto-Guérison Logicielle (APR 2024-2026)

### 1. Tests Métamorphiques pour Noyaux Numériques
- Dans les logiciels géométriques complexes (CAO, CFD, FEA), l'oracle de vérité terrain n'est pas toujours disponible sous forme de valeur exacte fermée.
- La vérification repose sur des **relations métamorphiques** fondamentales :
  - *Invariance par rotation* : $\text{Vol}(\mathcal{R}_\theta(S)) = \text{Vol}(S)$
  - *Idempotence booléenne* : $S \cup S = S$ et $S \cap S = S$
  - *Homogénéité dimensionnelle* : $\text{Vol}(k \cdot S) = k^3 \cdot \text{Vol}(S)$
- Si une modification viole l'une de ces relations métamorphiques sur un maillage aléatoire, une régression numérique est immédiatement diagnostiquée.

### 2. Réparation de Programmes Automatisée (APR) par Élimination de Régressions
- Classification formelle des patchs candidats :
  - *Patch Plausible* : Fait passer le test unitaire échoué mais peut introduire des régressions cachées.
  - *Patch Correct* : Fait passer le test échoué ET préserve 100% de la matrice de couverture et du Quality Gate ISO 25010 sans régression.

---

## ⚡ Patrons Avancés de Loop Engineering (Cherny & Steinberger 2026)

### 1. "Prompts Burn, Skills Compound"
- Les instructions données dans une invite brute (prompt) disparaissent avec la session ou polluent le contexte RAM.
- Toute correction structurelle, règle d'architecture ou nouveau workflow doit être cristallisé sous forme de **Skill modulaire** avec en-tête YAML léger ou consigné dans la mémoire vivante (`AI_ASSISTANT.md`). Chaque bug résolu devient un capital technique permanent.

### 2. Multiplexage d'Agents & Isolation par Git Worktrees
- Pour exécuter des audits massifs ou des refactorisations parallèles sans écraser les fichiers en cours d'édition :
  ```bash
  # Créer un arbre de travail Git isolé pour un sous-agent d'investigation
  git worktree add ../radiant-audit-branch -b audit/fea-depth
  ```
- L'agent travaille dans un bac à sable hermétique, exécute ses tests, puis fusionne ou soumet ses résultats sans polluer la branche active.

### 3. La Boucle Ralph Wiggum (Persistance Déterministe)
- Définition d'un signal d'arrêt booléen clair : l'agent réitère de manière continue tant que `exit_code != 0`.
- Éviter la dérive de contexte par rafraîchissement périodique : si la boucle dépasse 4 itérations, compacter l'historique en ne conservant que l'invariant brisé et la dernière trace d'erreur.

---

## 🧰 Outils & Références d'Accompagnement
- **Orchestrateur de Cycle Loopcraft** : [`scripts/run_loopcraft_cycle.py`](scripts/run_loopcraft_cycle.py) — exécute la cascade complète des barrières (typage, complexité, SAST, tests) et classifie les erreurs en 5 catégories.
- **Antisèche Opérationnelle** : [`references/loopcraft_cheatsheet.md`](references/loopcraft_cheatsheet.md) — commandes d'isolation par `git worktree`, taxonomie des 5 erreurs et patrons Ralph Wiggum.

---

## ⚠️ Anti-Patrons & Pièges Fréquents
1. **L'évaluation à l'aveugle (Blind Hallucination)** : Prétendre qu'un bogue est corrigé sans avoir exécuté le test dans le terminal réel avec code de retour 0.
2. **Le churn volumétrique destructeur** : Réécrire 200 lignes de code d'un fichier stable quand une correction chirurgicale de 3 lignes suffit, risquant d'introduire de nouvelles régressions.
3. **La dérive de contexte en boucle infinie** : Continuer à tenter des modifications aléatoires au-delà de 8 itérations sans s'arrêter pour documenter l'impasse et demander un arbitrage architectural.

---

## 🛡️ Règles de Survie en Mode Autonome

1. **Aucune Excuse, Analyse Factuelle** : En cas d'erreur de test, ne jamais s'excuser. Analyser immédiatement la trace d'appel (`traceback`), identifier la ligne exacte et la valeur des variables incriminées.
2. **Pas d'Évaluation à l'Aveugle** : Ne jamais supposer qu'un patch fonctionne sans avoir exécuté le test réel dans le terminal.
3. **Plafond d'Itérations Strict** : Si 8 tentatives échouent consécutivement, s'arrêter, résumer les 8 pistes explorées et leurs échecs respectifs, et poser une question ciblée à l'utilisateur.
4. **Idempotence des Migrations & Caches** : Chaque action doit être réversible et ne pas laisser de fichiers temporaires orphelins (`.tmp`).
