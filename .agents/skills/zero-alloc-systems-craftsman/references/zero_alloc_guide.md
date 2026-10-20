# Guide Technique : Ingénierie Zéro-Allocation & Haute Performance (2026)

Ce guide résume les règles matérielles et logicielles pour atteindre des débits maximaux dans les moteurs géométriques et viewports 3D (CAD Studio, PyOpenGL, NumPy, Rust).

---

## 1. La Hiérarchie Mémoire & Le Coût Réel des Objets Python

| Niveau Matériel | Temps d'Accès Latence | Bande Passante | Comportement en Python |
| :--- | :--- | :--- | :--- |
| **Registre CPU** | $\approx 0.5\text{ ns}$ | Extrême ($> 1\text{ To/s}$) | Variables locales scalaires pures |
| **Cache L1** | $\approx 1.5\text{ ns}$ | Très Élevée ($> 500\text{ Go/s}$) | Tableaux NumPy C-contigus compacts |
| **Cache L2** | $\approx 4\text{ ns}$ | Élevée ($> 200\text{ Go/s}$) | Slabs d'arènes topologiques B-Rep |
| **Cache L3** | $\approx 16\text{ ns}$ | Modérée ($> 80\text{ Go/s}$) | Maillages complets (jusqu'à 16 Mo) |
| **RAM Principale** | $\approx 60-100\text{ ns}$ | Limitée ($\approx 40\text{ Go/s}$) | Objets Python éparpillés sur le tas (*Heap fragmentation*) |

### Le Coût Caché de `[(x, y, z), ...]` :
- Une liste Python de $100\,000$ tuples de coordonnées 3D consomme plus de $8.5\text{ Mo}$ de RAM avec des pointeurs éparpillés, provoquant des défauts de cache constants (*Cache misses*).
- Un tableau NumPy `np.ndarray` `float32` de même taille consomme exactement **$1.2\text{ Mo}$** contigus d'un bloc, chargé en une seule rafale dans le cache L3 du processeur.

---

## 2. Techniques Zéro-Copie Clés

### 2.1 Utilisation Systématique de `np.ascontiguousarray`
Pour tout envoi vers OpenGL ou une bibliothèque C/Rust (comme Manifold3D) :
```python
# Forcer un tableau contigu en mémoire C (ordre row-major)
vbo_data = np.ascontiguousarray(vertices, dtype=np.float32)
```

### 2.2 Pré-Allocation et Cible `out=`
Dans les boucles de simulation FEA, cinématique ou déformation :
```python
# Allouer le tampon de destination UNE SEULE FOIS en amont
transformed_vertices = np.empty_like(base_vertices)

# Réutiliser le tampon à chaque pas de temps t sans allocation
for step in range(num_steps):
    np.matmul(base_vertices, rotation_matrix, out=transformed_vertices)
    renderer.update_vbo_subdata(transformed_vertices)
```

### 2.3 Streaming GPU par `glBufferSubData`
Ne jamais détruire et recréer les VBOs à 60 FPS :
```python
# Initialisation unique (capacité maximale)
glBindBuffer(GL_ARRAY_BUFFER, vbo_id)
glBufferData(GL_ARRAY_BUFFER, max_capacity_bytes, None, GL_DYNAMIC_DRAW)

# Rafraîchissement temps réel (Zéro allocation GPU)
glBindBuffer(GL_ARRAY_BUFFER, vbo_id)
glBufferSubData(GL_ARRAY_BUFFER, 0, actual_bytes, vertex_ptr)
```
