# Architecture PySide6 & Manifold3D pour CAD Studio (v7.0)

Ce guide détaille l'intégration d'un moteur de modélisation 3D temps réel avec Qt6/PySide6 selon les standards de performance 2026.

---

## 1. Découplage Thread UI & Calcul Géométrique (Typage Strict)

Pour éviter que l'interface graphique ne gèle lors d'opérations booléennes ou de découpes complexes (Union, Différence, Intersection CSG) :

```python
from dataclasses import dataclass
from typing import Final, Protocol
from PySide6.QtCore import QObject, QRunnable, Signal
import manifold3d as m

@dataclass(frozen=True)
class BooleanResult:
    """Résultat immuable d'une opération booléenne sur solide Manifold."""
    body: m.Manifold
    duration_ms: float
    is_watertight: bool

class BooleanWorkerSignals(QObject):
    """Signaux typés strictement sans jamais utiliser 'object' ou 'Any'."""
    finished: Final[Signal] = Signal(BooleanResult)
    error: Final[Signal] = Signal(str)

class BooleanWorker(QRunnable):
    """Travailleur d'arrière-plan exécuté sur le pool de threads Qt."""
    def __init__(self, body_a: m.Manifold, body_b: m.Manifold, operation: str) -> None:
        super().__init__()
        self._body_a: Final[m.Manifold] = body_a
        self._body_b: Final[m.Manifold] = body_b
        self._operation: Final[str] = operation
        self.signals: Final[BooleanWorkerSignals] = BooleanWorkerSignals()

    def run(self) -> None:
        import time
        t_start = time.perf_counter()
        try:
            if self._operation == "difference":
                res = self._body_a - self._body_b
            elif self._operation == "union":
                res = self._body_a + self._body_b
            elif self._operation == "intersection":
                res = self._body_a ^ self._body_b
            else:
                self.signals.error.emit(f"Opération inconnue : {self._operation}")
                return

            t_elapsed = (time.perf_counter() - t_start) * 1000.0
            mesh = res.to_mesh()
            is_closed = len(mesh.vert_properties) > 0 and len(mesh.tri_verts) > 0
            
            result = BooleanResult(
                body=res,
                duration_ms=t_elapsed,
                is_watertight=is_closed
            )
            self.signals.finished.emit(result)
        except Exception as exc:
            self.signals.error.emit(str(exc))
```

---

## 2. Rendu OpenGL Efficace dans QOpenGLWidget (Zero-Allocation VBO)

- Convertir le `Manifold` en maillage GPU via `mesh = result.to_mesh()`.
- Utiliser un tableau NumPy contigu en mémoire C : `vert_data = np.ascontiguousarray(mesh.vert_properties, dtype=np.float32)`.
- Téléverser les sommets et normales dans un tampon VBO OpenGL unique via `glBufferSubData` pour éviter toute réallocation de mémoire vidéo.
- Utiliser un shader PBR (Physically-Based Rendering) simple avec éclairage directionnel pour mettre en valeur les arêtes et chanfreins.
