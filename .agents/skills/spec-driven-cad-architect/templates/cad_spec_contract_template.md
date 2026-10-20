# Modèle de Spécification Formelle CAO (Contrat 4-Quadrants)

Ce modèle élimine le "vibe coding" en formalisant rigoureusement chaque nouvelle fonctionnalité géométrique avant son implémentation.

---

## Fonctionnalité : [Nom de la Feature / Opération]

### Quadrant 1 : Invariants Mathématiques & Topologiques
- **Invariant d'Euler-Poincaré** : $\chi = V - E + F = 2(1 - g)$ doit être conservé.
- **Continuité Géométrique** : Préciser le degré de continuité requis ($G^0$ position, $G^1$ tangence, $G^2$ courbure).
- **Étanchéité (Watertight)** : Zéro arête frontière orpheline (valence exactement 2 pour toute arête fermée).

### Quadrant 2 : Pré-Conditions & Gardes de Dégénérescence
- **Contraintes Dimensionnelles** : Paramètres d'entrée strictement positifs ($r > 10^{-4}\text{ mm}$).
- **Gardes Numériques** : Protection contre la division par zéro ($\max(\text{norm}, 10^{-12})$).
- **Validité Topologique des Entités Sélectionnées** : Arêtes non colinéaires, faces non auto-sécantes.

### Quadrant 3 : Post-Conditions & État Résultant
- **Volume Signé** : Volume strictement positif $\text{Vol} > 0$.
- **Boîte Englobante (AABB)** : L'enveloppe finale doit être cohérente avec les opérations appliquées.
- **Arbre de Construction** : L'opération doit produire un nœud d'entité réversible et sérialisable en JSON.

### Quadrant 4 : Tests de Caractérisation & Harnais de Régression
- **Cas Nominaux** : Test unitaire sur cube, cylindre et sphère canoniques.
- **Cas Limites (Edge Cases)** : Congé de rayon tangentiel limite, découpe coplanaire, géométrie rasante.
- **Performance & Allocation** : Zéro allocation superflue dans la boucle d'évaluation.
