# Guide des Conditions aux Limites & Solveurs Multi-Physiques (2026)

Ce guide résume la syntaxe des cartes de chargement CalculiX CCX et des conditions aux limites OpenFOAM.

---

## 1. Types d'Éléments Volumiques CalculiX

- `C3D4` : Tétraèdre linéaire à 4 nœuds. Rapide mais sujet au verrouillage de cisaillement (*shear locking*). À réserver aux pré-visualisations.
- `C3D10` : Tétraèdre quadratique à 10 nœuds. **Standard industriel recommandé** pour la précision des contraintes de von Mises en fond de gorge.
- `C3D8I` : Hexaèdre à 8 nœuds avec modes incompatibles. Précision maximale en flexion pure.

---

## 2. Syntaxe des Cartes de Chargement et Déplacements

```text
*BOUNDARY
# Format : Nœud/Set, DOF_Début, DOF_Fin, Valeur
NFIX, 1, 3, 0.0      # Encastrement complet (Dx = Dy = Dz = 0)
NPIN, 1, 2, 0.0      # Appui simple (Dx = Dy = 0, Dz libre)

*CLOAD
# Format : Nœud/Set, Direction (1=X, 2=Y, 3=Z), Valeur en Newtons
NFORCE, 2, -1500.0   # Force ponctuelle de 1500 N selon -Y
```

---

## 3. Conditions aux Limites OpenFOAM (Dossier `0/`)

| Grandeur Physique | Paroi Pièce (*Wall*) | Entrée Écoulement (*Inlet*) | Sortie Écoulement (*Outlet*) |
| :--- | :--- | :--- | :--- |
| **Vitesse $\mathbf{U}$** | `noSlip` (adhérence nulle) | `fixedValue; uniform (10 0 0);` | `zeroGradient;` |
| **Pression $p$** | `zeroGradient;` | `zeroGradient;` | `fixedValue; uniform 0;` |
| **Énergie Cinétique $k$** | `kLowReWallFunction;` | `fixedValue;` | `zeroGradient;` |
