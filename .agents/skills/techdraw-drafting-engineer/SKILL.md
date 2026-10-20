---
name: techdraw-drafting-engineer
description: >-
  Architect and implement 2D technical drawing generation (TechDraw), Sub-segmentary Hidden Line Removal (HLR), GD&T geometric tolerancing (ASME Y14.5 / ISO 1101), associative dimensioning, and sheet metal unfolding (K-factor, bend deduction).
---

# 📐 TechDraw Drafting & GD&T Tolerancing Engineer (SOTA 2026)

> **Standards :** ASME Y14.5-2018 / ISO 1101 (GD&T), ISO 128 (Dessin Technique), DIN 6935 (Tôlerie)  
> **Moteur :** Algorithme HLR Sub-Segmentaire Déterministe & Dépliage Neutre K-Factor  
> **Rôle :** Spécialiste de la projection 2D industrielle, de l'élimination des lignes cachées, du tolérancement géométrique et dimensionnel et du développement de tôle pliée.

---

## 🎯 Déclenchement & Cas d'Usage
Active ce skill pour toute tâche relative à :
- **Mise en Plan TechDraw 2D** : Projections orthogonales (Face, Dessus, Droite, Isométrique), coupes partielles et brisées, vues de détail à échelle variable.
- **Élimination des Lignes Cachées (HLR)** : Découpage sub-segmentaire des arêtes 3D masquées par les facettes avant, génération de tracés pointillés (`dashed`) ou suppression complète.
- **Tolérancement Géométrique GD&T** : Cadres de référence (*Feature Control Frames*), tolérances de forme (planéité, circularité, cylindricité), d'orientation (perpendicularité, parallélisme) et de localisation (position vraie au maximum de matière MMC).
- **Cotation Associative Paramétrique** : Cotes linéaires, angulaires, diamètres, rayons liés dynamiquement aux contraintes de l'esquisse et de l'arbre d'entités.
- **Tôlerie & Dépliage à Plat (Sheet Metal)** : Calcul de la fibre neutre $K$-factor, allongement de pli (*Bend Allowance* $BA$), perte au pli (*Bend Deduction* $BD$), et export DXF pour découpe laser/jet d'eau.

---

## 🏛️ Invariants Mathématiques du Dessin Technique

### 1. Fibre Neutre & Perte au Pli (Sheet Metal DIN 6935)
Pour une tôle d'épaisseur $T$, pliée selon un rayon intérieur $R_b$ et un angle de pli $\theta$ :
$$BA = \frac{\pi}{180} \cdot \theta \cdot (R_b + K \cdot T)$$
$$BD = 2(R_b + T) \tan\left(\frac{\theta}{2}\right) - BA$$
- **Plage Physique du K-Factor** : Pour les aciers et aluminiums standard, $0.25 \le K \le 0.50$ (valeur typique $K \approx 0.33$ à $0.42$).

### 2. Condition au Maximum de Matière (MMC $\text{Ⓜ}$) en GD&T
Pour un alésage de diamètre nominal $D$ avec tolérance $[D_{\min}, D_{\max}]$ et tolérance de position $t_0$ au MMC :
- Le MMC correspond à l'alésage le plus petit : $D_{\text{MMC}} = D_{\min}$.
- Si l'alésage réel usiné a un diamètre $D_{\text{actuel}} > D_{\min}$, la tolérance de position admissible s'élargit du bonus :
$$t_{\text{admissible}} = t_0 + (D_{\text{actuel}} - D_{\min})$$

### 3. Empilement de Tolérances 1D/3D (Tolerance Stack-up ASME Y14.5-2018)
- **Modèle du Pire des Cas (Worst-Case / Arithmetic Stack-up)** :
  $$T_{\text{wc}} = \sum_{i=1}^n |c_i| \cdot T_i$$
  Garantit 100% d'interchangeabilité mécanique sans aucun rebut en production.
- **Modèle Statistique RSS (Root-Sum-Square)** :
  $$T_{\text{rss}} = \sqrt{\sum_{i=1}^n (c_i \cdot T_i)^2}$$
  Pour les processus à capabilité maîtrisée ($C_p \ge 1.33$), réduit drastiquement les surcoûts d'usinage en prédisant une dispersion normale à $\pm 3\sigma$ (taux de non-conformité $< 0.27\%$).

---

## 🧰 Outils & Références d'Accompagnement
- **Vérificateur GD&T et Tôlerie** : [`scripts/verify_techdraw_gdt.py`](scripts/verify_techdraw_gdt.py) — contrôle les cadres de tolérances GD&T, calcule le $BD$ de tôlerie et valide les datums de référence.
- **Guide des Symboles GD&T ISO 1101** : [`references/gdt_iso1101_symbols.md`](references/gdt_iso1101_symbols.md) — tableau des 14 tolérances géométriques et abréviations normalisées.

---

## ⚠️ Anti-Patrons & Pièges Fréquents
1. **Le tracé continu des arêtes masquées** : Exporter les arêtes arrière sans découpage HLR sub-segmentaire, rendant le plan technique illisible et non conforme ISO 128.
2. **Le cadre de tolérance orphelin (Missing Datums)** : Définir une tolérance de localisation ou de perpendicularité sans spécifier de système de référence primaire ($A$), secondaire ($B$) ou tertiaire ($C$).
3. **Le K-factor hors bornes ($K > 0.50$)** : Utiliser un $K > 0.5$ suppose que la fibre neutre s'étire au-delà du centre de la tôle, violant les lois de déformation élasto-plastique des métaux.
