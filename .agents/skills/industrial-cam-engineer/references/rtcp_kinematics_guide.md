# Guide Cinématique RTCP 5-Axes & Post-Processeurs (2026)

Ce guide résume les configurations cinématiques des machines-outils CNC 5-axes et les codes de compensation RTCP.

---

## 1. Les 3 Architectures Cinématiques Majeures

1. **Table-Table (Trunnion / Berceau)** :
   - Les deux axes rotatifs ($A/C$ ou $B/C$) font pivoter la pièce.
   - La broche reste orientée le long de l'axe $Z$.
   - Équation de compensation : Inverse de la matrice de rotation combinée $\mathbf{R}_A \cdot \mathbf{R}_C$.

2. **Head-Head (Double Tête Pivotante)** :
   - La pièce reste fixe sur la table, la tête pivote selon $B$ et $C$.
   - Idéal pour les grandes pièces aéronautiques (longerons, nervures).
   - Déport de pivot $L_{\text{pivot}}$ constant ajouté au vecteur outil.

3. **Head-Table (Mixte)** :
   - La tête porte l'axe $B$, la table porte l'axe rotatif $C$.
   - Excellent compromis de rigidité pour l'outillage de moules et matrices.

---

## 2. Tableau de Correspondance des Post-Processeurs

| Marque / Commande Numérique | Activation RTCP | Désactivation RTCP | Format d'Arc 3D |
| :--- | :--- | :--- | :--- |
| **Fanuc 30i / 31i** | `G43.4 H01` | `G49` | Plans `G17`/`G18`/`G19` |
| **Heidenhain TNC 640** | `FUNCTION TCPM F CONT` ou `M128` | `M129` | `CP`, `CR`, `CT` |
| **Siemens Sinumerik 840D/ONE** | `TRAORI(1)` | `TRAFOOF` | `CIP` (Cercle par point intermédiaire) |
| **Haas NextGen (NGC)** | `G234 H01` (DWO) / `G43.4` | `G49` | `G02` / `G03` |
