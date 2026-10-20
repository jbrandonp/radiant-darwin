# Patrons d'Ancrage Neurosymbolique pour Logiciels CAO (2026)

Ce document détaille l'architecture reliant les grands modèles de langage (LLM) probabilistes aux noyaux géométriques déterministes (B-Rep / CSG).

---

## 1. Pourquoi le "Text-to-Mesh" Pur Échoue dans l'Industrie

- **Absence d'Arbre de Construction Paramétrique** : Les modèles génératifs purs (diffusion 3D, NeRF, point clouds) produisent des maillages denses non éditables, impossibles à modifier en atelier d'usinage.
- **Défaut de Raccord Tangentiel** : Les arrondis et raccords de surfaces ne respectent pas les continuités mathématiques $G^1$ (tangence) ou $G^2$ (courbure).
- **Le Choix Neurosymbolique** : Le modèle génère un **programme symbolique** (AST) appelant des primitives du noyau (`extrude`, `revolve`, `fillet`), puis le noyau géométrique résout la forme avec une précision machine à $10^{-9}$.

---

## 2. Transactions Atomiques & Retour Arrière (Rollback)

Toute commande générée par l'IA doit être encapsulée dans un périmètre transactionnel :
```python
from src.ai.cad_validator import AtomicTransactionScope

with AtomicTransactionScope(document) as txn:
    # 1. Exécution du script validé par l'AST
    part = document.add_cylinder(radius=10.0, height=50.0)
    # 2. Contrôle par oracles géométriques
    if not part.is_watertight():
        txn.rollback() # Annule l'ajout et restaure l'arbre d'origine
```
