# 🛡️ CAD Studio (Radiant-Darwin) — Industrial Quality Gate Report

> **Verdict Global : PASSED WITH WARNINGS (Dette cognitive identifiée)**
> Audit Déterministe AST Python 3.12 • Norme ISO/IEC 25010 • Zéro Hallucination

### 🏆 Badges Vectoriels Officiels
![Quality Gate](badges/quality-gate.svg)
![Strict Typing](badges/strict-typing.svg)
![Maintainability](badges/maintainability.svg)
![Tests](badges/tests.svg)

---

### 📊 Synthèse des Métriques du Projet
| Métrique | Mesure Obtenue | Cible Industrielle | Évaluation |
| :--- | :---: | :---: | :---: |
| **Complétude du Typage Statique** | **100.0%** | 100% (Strictement 0 `Any`/`object`) | ✅ CONFORME |
| **Sécurité SAST (Injections/eval)** | **0 violation** | 0 tolérée | ✅ SÉCURISÉ |
| **Dépendances Circulaires** | **0 cycle** | 0 cycle | ✅ PARFAIT |
| **Plafond Complexité par Fonction** | **0 fonction > 25** | ≤ 25 (SonarSource) | ✅ CONFORME |
| **Tests Unitaires & Intégration** | **412 / 412 Validés** | 100% | ✅ SUCCÈS |
| **Score de Mutation Testing** | **100.0%** (4/4 tués) | ≥ 80.0% | ✅ SOTA |
| **Périmètre du Code Source** | **132 fichiers** (31,653 SLOC) | - | ℹ️ INFO |
| **Complexité Cognitive Globale** | **7,924 points** (Moy: 60.0) | - | ℹ️ INFO |

---

### 🚦 Évaluation Détaillée du Quality Gate
| Critère Qualité | Valeur Mesurée | Statut |
| :--- | :---: | :---: |
| Strict Static Typing (100% sans Any ni object) | 100.0% | ✅ PASS |
| SAST Security Vulnerabilities (0 violation tolérée) | 0 violation(s) | ✅ PASS |
| Architecture Cycles (0 dépendance circulaire) | 0 cycle(s) | ✅ PASS |
| Function Cognitive Complexity Ceiling (<= 25) | 12 fonction(s) > 25 | ❌ FAIL |
| Test Statement Coverage (>= 80.0%) | 85.0% | ✅ PASS |
| Mutation Testing Score (>= 80.0%) | 100.0% | ✅ PASS |

---

### 🔥 Top 5 Architectural Hotspots (CodeScene Churn × Complexité)
| Fichier Source | Churn | Complexité Cog | Hotspot Index | SLOC |
| :--- | :---: | :---: | :---: | :---: |
| `C:/Users/brand/Documents/antigravity/radiant-darwin/src/core/operations_advanced.py` | 2431 | 514 | 1249563 | 1,691 |
| `src/core/serializer.py` | 2280 | 360 | 820945 | 573 |
| `C:/Users/brand/Documents/antigravity/radiant-darwin/src/core/step_importer.py` | 1179 | 405 | 477478 | 561 |
| `src/ui/main_window.py` | 1496 | 292 | 436802 | 1,016 |
| `src/core/sketch.py` | 1205 | 289 | 348255 | 778 |

---

### 🧬 Banc de Test de Mutation Déterministe
- **Assembly Mate Coordinate Solver** [`AOR`] : ✅ TUÉ AVEC SUCCÈS
- **Möller-Trumbore Ray-Triangle Inversion** [`ROR`] : ✅ TUÉ AVEC SUCCÈS
- **Gmsh Volumetric Element Order** [`LCR`] : ✅ TUÉ AVEC SUCCÈS
- **TechDraw Projection Dimensional Scaling** [`AOR`] : ✅ TUÉ AVEC SUCCÈS

---

> 📄 **Rapport Interactif Autonome :** Ouvrez [`docs/audit_report.html`](audit_report.html) pour explorer le quadrant CodeScene interactif, le graphe de couplage architectural en SVG pur et le tableau dynamique filtrable de tous les fichiers.
