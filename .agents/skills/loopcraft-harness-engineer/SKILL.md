---
name: loopcraft-harness-engineer
description: >-
  Use this skill when designing, setting up, or executing autonomous agentic loops, self-healing test harnesses, continuous verification pipelines, automated error classification (SYNTAX, RUNTIME, TEST_FAIL, LINT, SECURITY), or SonarQube / ISO 25010 Quality Gates. Enforces systematic plan-code-test-diagnose cycles with up to 8 bounded iterations.
---

# 🔁 Loopcraft & Self-Healing Harness Engineer (SOTA Octobre 2026)

> **Inspirations :** Addy Osmani (Loop Engineering & Loopcraft), Simon Willison (Eval-Driven Harnesses), Mitchell Hashimoto (Deterministic State Transitions)  
> **Standard :** Agentic Engineering Framework 2026  
> **Rôle :** Architecte des boucles de feedback autonomes, des harnais de tests auto-réparateurs et de la gouvernance de code par rétroaction déterministe.

---

## 🎯 Déclenchement & Cas d'Usage
Active ce skill pour :
- **Boucles d'auto-guérison (Self-Healing Loops)** : Résolution autonome de bugs, régression de tests, ou dette technique complexe sans supervision humaine constante.
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

# 2. Visiteur de typage statique strict (Zero-Any)
.venv\Scripts\python.exe scripts/strict_typing_visitor.py src/chemin/fichier_modifie.py

# 3. Analyseur de complexité cognitive & Quality Gate
.venv\Scripts\python.exe scripts/industrial_audit_engine.py
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

## 🛡️ Règles de Survie en Mode Autonome

1. **Aucune Excuse, Analyse Factuelle** : En cas d'erreur de test, ne jamais s'excuser. Analyser immédiatement la trace d'appel (`traceback`), identifier la ligne exacte et la valeur des variables incriminées.
2. **Pas d'Évaluation à l'Aveugle** : Ne jamais supposer qu'un patch fonctionne sans avoir exécuté le test réel dans le terminal.
3. **Plafond d'Itérations Strict** : Si 8 tentatives échouent consécutivement, s'arrêter, résumer les 8 pistes explorées et leurs échecs respectifs, et poser une question ciblée à l'utilisateur.
4. **Idempotence des Migrations & Caches** : Chaque action doit être réversible et ne pas laisser de fichiers temporaires orphelins (`.tmp`).
