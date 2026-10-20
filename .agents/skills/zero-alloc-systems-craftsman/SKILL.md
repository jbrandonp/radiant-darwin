---
name: zero-alloc-systems-craftsman
description: >-
  Architect and implement zero-allocation pipelines, high-performance C-contiguous NumPy buffer sharing, GPU VBO streaming, and C++/nanobind memory lifecycle management inspired by Armin Ronacher and Mitchell Hashimoto. Eliminates GC spikes, pointer copies, and memory leaks in numerical geometry engines.
---

# ⚡ Zero-Allocation Systems Craftsman (SOTA Octobre 2026)

> **Inspirations :** Armin Ronacher (*Fast and Hard Code*, *Build It Yourself*), Mitchell Hashimoto (*Ghostty* Systems Architecture & Direct Memory Control), Emmett Lalish (*Manifold3D* Memory Layout)  
> **Standard :** Systems Engineering 2026  
> **Rôle :** Maître de la performance bas niveau, de l'élimination des allocations mémoire dans les boucles critiques, du partage de mémoire tampon zéro-copie et de la gestion étanche du cycle de vie C++/Python.

---

## 🎯 Déclenchement & Cas d'Usage
Active ce skill pour :
- **Pipelines Géométriques à Haut Débit** : Manipulation de maillages de plus de $100\,000$ sommets, calculs de courbure NURBS, ou génération de trajectoires d'usinage 5-axes sans allocation superflue.
- **Partage Zéro-Copie NumPy / C++ / OpenGL** : Échange direct de pointeurs mémoire via le protocole tampon (`buffer protocol`, `memoryview`, `np.ascontiguousarray`) évitant toute duplication de données en RAM.
- **Élimination des Fuites Mémoire Nanobind / C++** : Éradication des avertissements de type `nanobind: leaked N instances of type manifold3d.Manifold` par gestion déterministe du cycle de vie des objets C++.
- **Streaming VBO Viewport 60/120 FPS** : Mise à jour fluide des tampons GPU OpenGL/Vulkan via `glBufferSubData` sans réallocation de tampons à chaque frame.
- **Arènes Mémoire Générationnelles** : Stockage contigu d'éléments topologiques B-Rep (sommets, arêtes, demi-arêtes) avec indexation $O(1)$ et réutilisation sans appel au ramasse-miettes (`gc`).

---

## 🏛️ Les 5 Piliers de l'Architecture Zéro-Allocation

```
┌─────────────────────────────────────────────────────────────┐
│ 1. Protocole Tampon & Zéro-Copie (NumPy C-Contiguous)       │
├─────────────────────────────────────────────────────────────┤
│ 2. Arènes Générationnelles & Réutilisation de Slabs         │
├─────────────────────────────────────────────────────────────┤
│ 3. Cycle de Vie C++ / Nanobind Déterministe (Zero Leaks)   │
├─────────────────────────────────────────────────────────────┤
│ 4. Streaming GPU VBO par Sous-Tampons (glBufferSubData)     │
├─────────────────────────────────────────────────────────────┤
│ 5. Profilage d'Allocation & Budget Mémoire Quantifié        │
└─────────────────────────────────────────────────────────────┘
```

---

### Pilier 1 : Protocole Tampon & Zéro-Copie NumPy
Dans les boucles de calcul géométrique (tessellation, normales de faces, transformations affines 4x4) :
- **Interdiction Formelle des Listes Python** : Ne jamais accumuler des coordonnées 3D dans des listes Python de tuples `[(x, y, z), ...]`. Chaque tuple génère un objet Python distinct sur le tas (`heap overhead` de 48+ octets par sommet).
- **Tableaux Contigus en C** : Toujours forcer l'alignement C-contiguous :
  ```python
  vertices_c = np.ascontiguousarray(vertices, dtype=np.float32)
  ```
- **Vues Mémoire (`memoryview`)** : Utiliser `memoryview(arr)` ou `arr.view()` pour passer des tranches de données aux extensions C++ ou à OpenGL sans copier les octets sous-jacents.

### Pilier 2 : Arènes Générationnelles & Indexation $O(1)$
- **Interdiction du `malloc`/`free` Fréquent** : Pour les structures topologiques B-Rep soumises à de fortes variations (itérations de découpe booléenne, maillage dynamique), allouer des blocs contigus de mémoire (*slabs*).
- **Indexation par Entier 32-bits** : Référencer les sommets et arêtes par un identifiant d'arène `(index: int, generation: int)` plutôt que par des références d'objets circulaires Python.
- **Réutilisation de Tampons Pré-Alloués** :
  ```python
  # Pré-allouer la matrice de transformation pour réutilisation
  out_buffer = np.empty_like(input_coords)
  np.matmul(input_coords, transform_matrix, out=out_buffer)
  ```

### Pilier 3 : Cycle de Vie C++ / Nanobind Déterministe
Les bibliothèques C++ modernes (comme Manifold3D ou OpenCASCADE) interfacées avec Python via `nanobind` ou `pybind11` conservent des compteurs de références internes :
- **Le Danger des Références Fantômes** : Si un objet `Manifold` est stocké dans un dictionnaire global, un cache non invalidé, ou une clôture d'événement Qt (`lambda`), le ramasse-miettes Python ne peut pas libérer la mémoire C++ sous-jacente, causant des fuites lors de la fermeture de la fenêtre.
- **Règle Déterministe de Libération** :
  1. Toujours découpler les objets géométriques lourds des widgets graphiques.
  2. Fournir une méthode explicite `dispose()` ou `close()` qui détache les pointeurs natifs.
  3. Utiliser un gestionnaire de contexte (`with native_session():`) lors des opérations de calcul intensif en arrière-plan.

### Pilier 4 : Streaming GPU VBO sans Réallocation
Dans le viewport PyOpenGL :
- **Ne JAMAIS Recréer les VBOs à Chaque Frame** :
  - Mauvais : `vbo_id = glGenBuffers(1); glBufferData(GL_ARRAY_BUFFER, ...)` à chaque changement de zoom ou d'angle.
  - Correct : Allouer un VBO de capacité maximale initiale, puis utiliser `glBufferSubData(GL_ARRAY_BUFFER, 0, actual_size, data_ptr)` pour mettre à jour les coordonnées sans réallouer la mémoire vidéo.
- **Interleaved Vertex Buffers** : Entrelacer les attributs `[X, Y, Z, Nx, Ny, Nz, R, G, B]` dans un seul tampon pour maximiser la localité de cache de la carte graphique (L1/L2 GPU cache).

### Pilier 5 : Profilage d'Allocation & Budgets Mémoire
- **Vérification d'Allocation Zéro dans les Boucles** :
  ```python
  import tracemalloc

  tracemalloc.start()
  snapshot_before = tracemalloc.take_snapshot()

  # Exécution de la boucle géométrique critique
  kernel.evaluate_nurbs_grid(u_samples=100, v_samples=100)

  snapshot_after = tracemalloc.take_snapshot()
  top_stats = snapshot_after.compare_to(snapshot_before, 'lineno')
  # Le delta d'allocation doit être de 0 octet dans les fonctions d'évaluation pure
  ```
- **Plafond Mémoire Strict** : Une session CAD Studio ne doit jamais dépasser $512\text{ Mo}$ de RAM pour un assemblage de 50 pièces standard.

---

## 🔬 Fondements Scientifiques des Architectures Mémoire (2024-2026)

### 1. Disposition Structure of Arrays (SoA) vs Array of Structures (AoS)
Dans le traitement géométrique intensif (traversée BVH, projection de sommets) :
- **AoS ($[(X, Y, Z, N_x, N_y, N_z), ...]$)** pollue le cache L1 en chargeant des normales et attributs superflus lors du balayage des seules coordonnées spatiales.
- **SoA ($\mathbf{X} = [x_0, x_1, ...], \mathbf{Y} = [y_0, y_1, ...], \mathbf{Z} = [z_0, z_1, ...]$)** permet un chargement direct dans les registres vectoriels SIMD 512-bits (AVX-512 / ARM Neon) sans surcoût de réalignement (*shuffle overhead*), saturant la bande passante maximale de la DRAM.

### 2. Hiérarchies Spatiales Cache-Oblivious (Agencement de van Emde Boas)
- Minimise les transferts de mémoire vers le cache avec une borne asymptotique optimale $Q(N) = O(N/B)$ pour un arbre spatial à $N$ nœuds sans nécessiter la calibration manuelle de la taille de ligne de cache $B$ ou de la capacité mémoire $M$.
- Subdivise récursivement la hiérarchie de boîtes englobantes (BVH) en sous-arbres stockés de manière contiguë en mémoire vive, garantissant une traversée optimale sur l'ensemble des niveaux L1, L2, L3 et RAM.

---

## 🧰 Outils & Références d'Accompagnement
- **Profiler Mémoire Zéro-Allocation** : [`scripts/profile_zero_alloc.py`](scripts/profile_zero_alloc.py) — mesure déterministe des deltas d'allocation heap et vérification de contiguïté C des matrices NumPy.
- **Guide Haute Performance Mémoire** : [`references/zero_alloc_guide.md`](references/zero_alloc_guide.md) — hiérarchie des caches processeur, protocoles de tampons et streaming VBO GPU.

---

## ⚠️ Anti-Patrons & Pièges Fréquents
1. **Le faux zéro-copie de l'indexation avancée (Fancy Indexing)** : `arr[mask]` ou `arr[[0, 1, 2]]` crée toujours une copie mémoire complète en NumPy. Seul le slicing régulier (`arr[::2]`) produit une vue sans allocation.
2. **La fuite native par clôture Qt (Lambda Leak)** : Capturer un pointeur d'objet C++ Manifold3D dans un slot Qt sans déconnexion explicite maintient l'objet vivant indéfiniment en RAM.
3. **La réallocation de tampons OpenGL dans `paintGL`** : Appeler `glGenBuffers` ou `glBufferData` à chaque rafraîchissement d'écran provoque des saccades d'affichage (*frame drops*) et sature la mémoire du pilote.

---

## 🛡️ Règles d'Or pour le Développeur
1. **Pense au Cache L1/L2 du Processeur** : La mémoire séquentielle et contiguë est 100 à 200 fois plus rapide que la traversée de pointeurs dispersés en mémoire vive.
2. **Évite les Conversions Implicites** : Attention aux conversions `float64` vers `float32` qui dupliquent silencieusement un tableau NumPy entier.
3. **Respecte la Règle Zéro Docker** : Toute l'optimisation doit fonctionner en natif pur sur la machine de Brandon avec Python 3.12, `uv`, et les extensions compilées locales.
