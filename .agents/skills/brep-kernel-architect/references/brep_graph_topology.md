# Architecture Topologique B-Rep : Half-Edge & Invariants d'Euler (2026)

Ce document formalise les relations de connectivité du graphe de frontière (BRepGraph) et les formules d'Euler-Poincaré pour solides orientables.

---

## 1. La Structure de Données Demi-Arête (Half-Edge)

Chaque arête frontière est dédoublée en deux demi-arêtes orientées en sens opposé :
- `origin` : Sommet de départ de la demi-arête.
- `twin` : Demi-arête jumelle appartenant à la face adjacente.
- `next` : Demi-arête suivante bordant la même face (sens trigonométrique).
- `face` : Face bordée par cette demi-arête.

### Invariants Topologiques Obligatoires :
$$\forall e, \quad e.\text{twin}.\text{twin} = e$$
$$\forall e, \quad e.\text{next}.\text{origin} = e.\text{twin}.\text{origin}$$
$$\forall e, \quad \exists k \ge 3 \text{ tel que } e.\text{next}^{(k)} = e \quad (\text{Boucle fermée})$$

---

## 2. Invariant d'Euler-Poincaré Généralisé

Pour tout corps solide complexe comportant des anneaux internes, des trous traversants et plusieurs coques :
$$V - E + F - (L - F) = 2(S - G)$$
Où :
- $V$ : Nombre de sommets (*Vertices*).
- $E$ : Nombre d'arêtes (*Edges*).
- $F$ : Nombre de faces (*Faces*).
- $L$ : Nombre total de boucles de contour (*Loops*, extérieures + trous intérieurs).
- $S$ : Nombre de coques fermées disjointes (*Shells*).
- $G$ : Genre topologique global (nombre de passages traversants, équivalent au tore si $G=1$).
