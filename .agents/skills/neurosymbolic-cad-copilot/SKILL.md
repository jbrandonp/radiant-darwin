---
name: neurosymbolic-cad-copilot
description: >-
  Use this skill when translating natural language prompts into parametric CAD models, generating mechanical parts (gears, heat sinks, brackets, enclosures) via CADAIBridge, validating generative CAD scripts with AST sandboxing (cad_validator), or orchestrating multi-step AI design synthesis with automated rollback and visual feedback.
---

# 🧠 Neurosymbolic CAD Copilot (SOTA Octobre 2026)

> **Inspirations :** Andrej Karpathy (Software 3.0 & Symbolic Grounding), Autodesk Research (BrepGen & SolidGen), DualBrep & FutureCAD (ICML 2026)  
> **Standard :** Correct-by-Construction Generative CAD Architecture  
> **Rôle :** Passerelle neurosymbolique reliant les modèles de langage à grand contexte aux moteurs géométriques déterministes (Manifold3D, B-Rep, solveurs de contraintes).

---

## 🎯 Déclenchement & Cas d'Usage
Active ce skill pour :
- **Synthèse de Pièces par Langage Naturel** : Transformer des requêtes utilisateur ("Crée un carter électronique 120x80x40 mm avec 4 bossages de fixation M3 et un joint d'étanchéité") en arbres paramétriques rigoureux.
- **Exécution Sécurisée de Scripts CAO (AST Sandboxing)** : Valider les scripts générés via `CADValidator` pour interdire tout accès système dangereux (`os.system`, `subprocess`, fuites réseau).
- **Transactions Atomiques & Auto-Rollback** : Envelopper toute modification issue de l'IA dans un `AtomicTransactionScope` pour annuler instantanément les opérations en cas d'erreur topologique.
- **Validation Visuelle & Topologique Fermée** : Vérifier avec `AIVisionFeedback` et `ShapeFixer` que le solide résultat est étanche (0 arête frontière, genre $g$ préservé, volume $> 0$).

---

## 🏛️ Les 3 Piliers du Paradigme Neurosymbolique

```
[1. NEURAL / LLM INTENT]
   "Génère une bride de tuyauterie DN50 4 trous"
           │
           ▼
[2. SYMBOLIC GROUNDING & VALIDATION]
   - Parseur de dimensions et contraintes
   - AST Validator (Sandbox pure)
   - Contrat géométrique Karpathy (Invariants)
           │
           ▼
[3. DETERMINISTIC CAD EXECUTION]
   - CADAIBridge & ShapeSynthesizer
   - Manifold3D Exact CSG / NexusBRep
   - AtomicTransactionScope (Commit ou Rollback)
```

1. **Intention Sémantique (Neural)** : L'IA comprend le vocabulaire métier ("flasque", "nervure", "dépouille", "pas métrique").
2. **Ancrage Symbolique (Symbolic)** : Les intentions sont converties en appels stricts d'`AICommandType` ou en nœuds de l'arbre paramétrique de `CADDocument`.
3. **Exécution Déterministe (Physical Kernel)** : Le solide final est garanti variétal (manifold), sans approximations ni hallucinations géométriques.

---

## 🛠️ Composants Clés dans `src/ai/`

- **Passerelle Centrale** : [`src/ai/cad_ai_bridge.py`](src/ai/cad_ai_bridge.py) (`CADAIBridge`, `AICommandType`).
- **Générateur de Pièces Industrielles** : [`src/ai/shape_synthesizer.py`](src/ai/shape_synthesizer.py) (engrenages, dissipateurs thermiques, paliers, carters).
- **Validateur de Sécurité AST** : [`src/ai/cad_validator.py`](src/ai/cad_validator.py) (`CADValidator`, `ValidationReport`).
- **Stabilité & Transactions Atomiques** : [`src/ai/cad_ai_stability.py`](src/ai/cad_ai_stability.py) (`AtomicTransactionScope`, `CADTransactionManager`).
- **Retour Visuel Multimodal** : [`src/ai/ai_vision_feedback.py`](src/ai/ai_vision_feedback.py) (`AIVisionFeedback`).
- **Protocole MCP Stdio** : [`src/ai/mcp_stdio.py`](src/ai/mcp_stdio.py) (connexion JSON-RPC / MCP pour outils externes).

---

## 📋 Protocole d'Exécution en 4 Phases

### Phase 1 : Décomposition de la Requête en Commandes Déclaratives
- Extraire les dimensions clés (longueur, largeur, hauteur, rayons de congés, diamètres de perçage).
- Déterminer la pièce maîtresse et les opérations booléennes associées :
  ```python
  from src.ai.cad_ai_bridge import CADAIBridge, AICommandType
  bridge = CADAIBridge(document)
  ```

### Phase 2 : Validation AST Préalable (Si génération de script Python)
- Si l'IA génère du code de script CAO autonome, soumettre impérativement le code à `CADValidator` :
  ```python
  report = CADValidator.validate_script_code(user_script)
  if not report.is_safe:
      raise SecurityError(f"Script non sécurisé : {report.violations}")
  ```

### Phase 3 : Exécution Transactionnelle Atomique
- Toujours encadrer les commandes de l'IA dans un `AtomicTransactionScope` :
  ```python
  with AtomicTransactionScope(document, "AI_Feature_Generation"):
      # Exécution des opérations
      res = bridge.execute_command(AICommandType.SYNTHESIZE_SHAPE, params)
  ```
- En cas d'exception ou de maillage non-étanche, le scope restaure automatiquement l'état précédent du document sans corrompre la session utilisateur.

### Phase 4 : Contrôle Qualité de Sortie (Watertight Check)
- Vérifier que le solide généré n'est pas vide et possède un volume positif.
- Si nécessaire, invoquer `ShapeFixer.heal_solid(res.solid)` pour refermer d'éventuelles micro-fissures de calcul.

---

## 🔬 Avancées Scientifiques de Synthèse CAO Neurosymbolique (CVPR & SIGGRAPH 2024-2026)

### 1. Apprentissage par Renforcement Multi-Experts (CME-CAD, CVPR)
- Combine un pré-entraînement supervisé multi-experts (MEFT) et un apprentissage par renforcement (MERL) évaluant la fidélité de reconstruction 3D sans approximation polygonale.
- Utilise des oracles d'exécution symboliques (Manifold3D / B-Rep) comme signaux de récompense denses pour guider la génération de code paramétrique directement éditable.

### 2. Séquençage par Pointeurs Topologiques (Pointer-CAD, CVPR)
- Élimine les erreurs de discrétisation de coordonnées continues en modélisant les références d'esquisse et de protrusion comme des pointeurs discrets explicites dans le graphe d'entités.
- Empêche les bifurcations topologiques catastrophiques lors des opérations d'extrusion et de révolution chaînées.

---

## 🧰 Outils & Références d'Accompagnement
- **Validateur AST de Script IA** : [`scripts/validate_cad_prompt_ast.py`](scripts/validate_cad_prompt_ast.py) — contrôle l'ancrage dans les primitives CAO autorisées et bloque les méthodes privées.
- **Guide d'Ancrage Neurosymbolique** : [`references/neurosymbolic_patterns.md`](references/neurosymbolic_patterns.md) — patrons d'arbre d'entités, DSL et transactions atomiques avec rollback.

---

## ⚠️ Anti-Patrons & Pièges Fréquents
1. **L'appel direct aux méthodes privées internes** : Tenter d'invoquer `doc._destroy_all()` ou `doc._raw_manifold` au lieu d'utiliser l'API publique (`doc.add_box()`, `doc.cut()`).
2. **L'omission de transaction atomique** : Modifier l'arbre du document directement sans `AtomicTransactionScope`, laissant une pièce corrompue dans l'interface si l'opération finale échoue.
3. **Le piège du "Text-to-Mesh" sans arbre paramétrique** : Générer un maillage de polygones non paramétrique au lieu d'un script d'opérations géométriques réversibles.
