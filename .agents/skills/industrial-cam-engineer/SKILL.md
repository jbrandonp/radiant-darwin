---
name: industrial-cam-engineer
description: >-
  Architect and implement 5-axis CNC machining pipelines, RTCP kinematics, G-code post-processors (Fanuc, Heidenhain, Siemens), toolpath collision gouge checking, metrology CMM inspection, and fiber placement (AFP).
---

# ⚙️ Industrial CAM & 5-Axis Manufacturing Engineer (SOTA 2026)

> **Standard :** ISO 6983 G-Code, ISO 14649 STEP-NC, DIN 66025  
> **Cinématique :** RTCP Continu (Rotation Tool Center Point / Tool Tip Tracking)  
> **Rôle :** Spécialiste de la fabrication assistée par ordinateur (FAO), des trajectoires d'usinage multi-axes, des post-processeurs industriels et de la métrologie tridimensionnelle.

---

## 🎯 Déclenchement & Cas d'Usage
Active ce skill pour toute tâche relative à :
- **Cinématique RTCP 5-Axes** : Compensation en temps réel de la longueur d'outil ($L_{\text{tool}}$) et des déports de tables rotatives/têtes pivotantes (Fanuc `G43.4`, Heidenhain `M128`, Siemens `TRAORI`).
- **Génération & Lissage de Trajectoires** : Ébauche adaptative en spirale, finition à hauteur de crête constante (*Constant Scallop*), interpolation d'arcs hélicoïdaux (G02/G03 en 3D).
- **Post-Processeurs Industriels** : Formatage des blocs G-code conformes aux machines Fanuc 31i, Siemens 840D/ONE, Heidenhain TNC 640 et Haas NGC.
- **Détection de Collision & Talonnement (Gouge Checking)** : Évitement des interférences entre le porte-outil (*holder*), la pièce usinée et le brut restant (*stock voxels*).
- **Métrologie CMM & Recalage ICP** : Alignement de nuages de points palpés avec le modèle B-Rep nominal par algorithme ICP (*Iterative Closest Point*) et calcul d'écarts thermiques.
- **Placement Automatisé de Fibres (AFP)** : Trajectoires de dépose géodésique de rubans composites sans plissement (*steering buckling*).

---

## 🏛️ Invariants Mathématiques de la FAO 5-Axes

### 1. Équation Fondamentale du RTCP (Tool Center Point)
Dans une machine à cinématique tête-table ou double-tête, la position de la pointe d'outil dans l'espace pièce $\mathbf{P}_{\text{workpiece}}$ est reliée au pivot de broche $\mathbf{P}_{\text{pivot}}$ par le vecteur outil orienté $\mathbf{V}_{\text{tool}} = (\sin B \cos C, \sin B \sin C, \cos B)$ et la longueur d'outil $L_{\text{tool}}$ :
$$\mathbf{P}_{\text{pivot}} = \mathbf{P}_{\text{tip}} + L_{\text{tool}} \cdot \mathbf{V}_{\text{tool}}$$
$$\mathbf{P}_{\text{machine}} = \mathbf{R}_{\text{table}}^{-1} \cdot (\mathbf{P}_{\text{pivot}} - \mathbf{O}_{\text{table}})$$

### 2. Hauteur de Crête (Scallop Height) & État de Surface
Pour une fraise hémisphérique de rayon $R$ et un pas latéral $s$ (*stepover*) :
$$h_{\text{scallop}} = R - \sqrt{R^2 - \frac{s^2}{4}} \approx \frac{s^2}{8 R}$$
- Pour une rugosité visée $Ra \le 0.8\,\mu\text{m}$, le pas latéral doit satisfaire :
$$s \le \sqrt{32 \cdot R \cdot Ra}$$

### 3. Planification à Jerk Minimal & Espaces SMM (Recherche 2024-2026)
- **Lissage à Jerk Minimal ($J = \dddot{X}$)** : L'accélération et le jerk angulaire ($\dot{\boldsymbol{\omega}}$) sont minimisés par programmation quadratique par morceaux le long des splines d'usinage, réduisant les vibrations de crête de plus de 22% sur les pièces à parois minces.
- **Espaces Découplés Maître-Esclave (SMM)** : Découplage de la position du point de contact (TCP) et de l'axe d'inclinaison sur des courbes de Bézier duales avec condition de monotonie de courbure pour éliminer les marques de broutage (*micro-chatter*).

---

## 🧰 Outils & Références d'Accompagnement
- **Vérificateur de Trajectoires d'Usinage** : [`scripts/verify_cam_toolpath.py`](scripts/verify_cam_toolpath.py) — contrôle de continuité des trajectoires, estimation du temps d'usinage, et détection des inversions brusques d'orientation d'outil.
- **Guide Cinématique RTCP & Post-Processeurs** : [`references/rtcp_kinematics_guide.md`](references/rtcp_kinematics_guide.md) — matrices de transformation par type de cinématique (Table-Table, Head-Table, Head-Head).

---

## ⚠️ Anti-Patrons & Pièges Fréquents
1. **La singularité du C-Axis Flip au zénith** : Lorsque l'outil est vertical ($B = 0^\circ$), l'angle $C$ est indéterminé. Une mauvaise interpolation fait tourner l'axe $C$ de $180^\circ$ instantanément, brisant l'outil ou endommageant la pièce.
2. **Le talonnement du porte-outil (Toolholder Gouge)** : Ne vérifier la collision que sur la pointe de coupe sans tester l'enveloppe du cône porte-outil (HSK/BT40).
3. **L'omission de compensation de rayon d'outil en 3D** : Confondre la trajectoire du centre de la fraise avec le point de contact réel sur la surface usinée.
