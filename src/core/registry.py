"""
Registre Central des Composants et Ateliers (Lego Registry).
Permet d'enregistrer, d'inspecter et d'instancier dynamiquement chaque brique de CAD Studio
(Features volumiques, Ateliers métiers, Exportateurs) sans couplage fort.
Typage nominal strict et fabriques paramétriques.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Dict, List, Tuple, Optional, Callable, Type, Union

FeatureArg = Union[str, int, float, bool, Tuple[float, ...], List[float], List[str]]

from src.core.interfaces import WorkbenchModule
from src.core.feature import Feature


class FeatureCategory(Enum):
    """Catégories de fonctionnalités volumiques LEGO."""
    PRIMITIVE = "primitive"      # Formes de base (Boîte, Cylindre, Sphère, Cône, Tore, Coin)
    SKETCH_BASED = "sketch"      # Extrusion, Révolution, Lissage, Balayage, Nervure
    MODIFICATION = "modify"      # Congé, Chanfrein, Dépouille, Évidement, Perçage, Découpe
    PATTERN = "pattern"          # Répétitions linéaires, circulaires, miroirs, multi-transform
    SHEET_METAL = "sheetmetal"   # Tôlerie pliée
    HARDWARE = "hardware"        # Visserie et fixations normalisées


@dataclass(frozen=True)
class FeatureDescriptor:
    """Description métadonnée d'une brique de fonctionnalité paramétrique."""
    class_name: str
    display_name: str
    category: FeatureCategory
    description: str
    icon_name: str
    factory: Callable[..., Feature]


class FeatureRegistry:
    """
    Registre unifié de toutes les opérations paramétriques du logiciel.
    Permet l'instanciation dynamique et la découverte automatique par l'IHM.
    """

    _registry: Dict[str, FeatureDescriptor] = {}

    @classmethod
    def register(
        cls,
        class_name: str,
        display_name: str,
        category: FeatureCategory,
        description: str,
        icon_name: str,
        factory: Callable[..., Feature]
    ) -> None:
        """Enregistre un descripteur de fonctionnalité."""
        descriptor = FeatureDescriptor(
            class_name=class_name,
            display_name=display_name,
            category=category,
            description=description,
            icon_name=icon_name,
            factory=factory
        )
        cls._registry[class_name] = descriptor

    @classmethod
    def get(cls, class_name: str) -> Optional[FeatureDescriptor]:
        """Récupère le descripteur d'une classe par son nom."""
        return cls._registry.get(class_name)

    @classmethod
    def create(cls, class_name: str, *args: FeatureArg, **kwargs: FeatureArg) -> Optional[Feature]:
        """Instancie dynamiquement une fonctionnalité via sa fabrique enregistrée."""
        descriptor = cls._registry.get(class_name)
        if descriptor is None:
            return None
        try:
            return descriptor.factory(*args, **kwargs)
        except Exception as err:
            print(f"[FeatureRegistry] Erreur création de {class_name} : {err}")
            return None

    @classmethod
    def list_all(cls) -> List[FeatureDescriptor]:
        """Retourne la liste de tous les descripteurs enregistrés."""
        return list(cls._registry.values())

    @classmethod
    def list_by_category(cls, category: FeatureCategory) -> List[FeatureDescriptor]:
        """Retourne les fonctionnalités appartenant à une catégorie spécifique."""
        return [desc for desc in cls._registry.values() if desc.category == category]

    @classmethod
    def is_registered(cls, class_name: str) -> bool:
        """Vérifie si une classe est déjà enregistrée."""
        return class_name in cls._registry


@dataclass(frozen=True)
class WorkbenchDescriptor:
    """Description métadonnée d'un atelier métier enfichable."""
    workbench_id: str
    title: str
    category: str
    icon_name: str
    instance: WorkbenchModule


class WorkbenchRegistry:
    """
    Registre des ateliers métiers LEGO (FEA, TechDraw, CAM, SheetMetal, Assembly).
    """

    _workbenches: Dict[str, WorkbenchDescriptor] = {}

    @classmethod
    def register(
        cls,
        workbench_id: str,
        title: str,
        category: str,
        icon_name: str,
        instance: WorkbenchModule
    ) -> None:
        """Enregistre un atelier métier modulaire."""
        desc = WorkbenchDescriptor(
            workbench_id=workbench_id,
            title=title,
            category=category,
            icon_name=icon_name,
            instance=instance
        )
        cls._workbenches[workbench_id] = desc

    @classmethod
    def get(cls, workbench_id: str) -> Optional[WorkbenchDescriptor]:
        """Récupère un atelier par son identifiant unique."""
        return cls._workbenches.get(workbench_id)

    @classmethod
    def list_all(cls) -> List[WorkbenchDescriptor]:
        """Liste tous les ateliers enregistrés."""
        return list(cls._workbenches.values())


def bootstrap_default_features() -> None:
    """Enregistre les fonctionnalités natives de CAD Studio dans le FeatureRegistry."""
    from src.core.feature import (
        BoxFeature, CylinderFeature, SphereFeature, ConeFeature, TorusFeature,
        WedgeFeature, ExtrudeFeature, BooleanFeature
    )
    from src.core.operations_advanced import (
        RevolveFeature, LinearPatternFeature, CircularPatternFeature, MirrorFeature,
        HoleFeature, ShellFeature, FilletFeature, ChamferFeature, DraftFeature,
        PocketFeature, DatumPlaneFeature, GrooveFeature, MultiTransformFeature,
        HelixFeature, RibFeature, SplitFeature, LoftFeature, SubtractiveLoftFeature,
        SweepFeature, SubtractiveSweepFeature
    )
    from src.sheetmetal.sheet_metal import SheetMetalFeature
    from src.core.fasteners import FastenerFeature

    # Primitives
    FeatureRegistry.register(
        "BoxFeature", "Boîte Parallélépipédique", FeatureCategory.PRIMITIVE,
        "Crée un bloc cubique ou pavé droit paramétrique", "cube",
        lambda *args, **kwargs: BoxFeature(*args, **kwargs)  # type: ignore[arg-type]
    )
    FeatureRegistry.register(
        "CylinderFeature", "Cylindre Paramétrique", FeatureCategory.PRIMITIVE,
        "Crée un cylindre de révolution", "cylinder",
        lambda *args, **kwargs: CylinderFeature(*args, **kwargs)  # type: ignore[arg-type]
    )
    FeatureRegistry.register(
        "SphereFeature", "Sphère", FeatureCategory.PRIMITIVE,
        "Crée une sphère solide étanche", "sphere",
        lambda *args, **kwargs: SphereFeature(*args, **kwargs)  # type: ignore[arg-type]
    )
    FeatureRegistry.register(
        "ConeFeature", "Cône / Tronc de Cône", FeatureCategory.PRIMITIVE,
        "Crée un cône droit ou tronqué", "cone",
        lambda *args, **kwargs: ConeFeature(*args, **kwargs)  # type: ignore[arg-type]
    )
    FeatureRegistry.register(
        "TorusFeature", "Tore", FeatureCategory.PRIMITIVE,
        "Crée un tore circulaire paramétrique", "circle",
        lambda *args, **kwargs: TorusFeature(*args, **kwargs)  # type: ignore[arg-type]
    )
    FeatureRegistry.register(
        "WedgeFeature", "Coin / Prisme", FeatureCategory.PRIMITIVE,
        "Crée une rampe ou un coin trapézoïdal", "triangle",
        lambda *args, **kwargs: WedgeFeature(*args, **kwargs)  # type: ignore[arg-type]
    )

    # Basées sur esquisses
    FeatureRegistry.register(
        "ExtrudeFeature", "Extrusion (Pad)", FeatureCategory.SKETCH_BASED,
        "Extrude un profil d'esquisse fermée", "extrude",
        lambda *args, **kwargs: ExtrudeFeature(*args, **kwargs)  # type: ignore[arg-type]
    )
    FeatureRegistry.register(
        "RevolveFeature", "Révolution (Revolve)", FeatureCategory.SKETCH_BASED,
        "Fait tourner un profil 2D autour d'un axe", "revolve",
        lambda *args, **kwargs: RevolveFeature(*args, **kwargs)  # type: ignore[arg-type]
    )
    FeatureRegistry.register(
        "LoftFeature", "Lissage Additif (Loft)", FeatureCategory.SKETCH_BASED,
        "Génère un volume lissé entre deux profils", "loft",
        lambda *args, **kwargs: LoftFeature(*args, **kwargs)  # type: ignore[arg-type]
    )
    FeatureRegistry.register(
        "SubtractiveLoftFeature", "Lissage Soustractif", FeatureCategory.SKETCH_BASED,
        "Creuse une cavité lissée entre profils", "loft_cut",
        lambda *args, **kwargs: SubtractiveLoftFeature(*args, **kwargs)  # type: ignore[arg-type]
    )
    FeatureRegistry.register(
        "SweepFeature", "Balayage (Sweep)", FeatureCategory.SKETCH_BASED,
        "Balaie un contour le long d'une trajectoire", "sweep",
        lambda *args, **kwargs: SweepFeature(*args, **kwargs)  # type: ignore[arg-type]
    )
    FeatureRegistry.register(
        "SubtractiveSweepFeature", "Balayage Soustractif", FeatureCategory.SKETCH_BASED,
        "Creuse une gorge le long d'une trajectoire", "sweep_cut",
        lambda *args, **kwargs: SubtractiveSweepFeature(*args, **kwargs)  # type: ignore[arg-type]
    )
    FeatureRegistry.register(
        "RibFeature", "Nervure de Renfort (Rib)", FeatureCategory.SKETCH_BASED,
        "Ajoute un gousset ou une nervure de rigidification", "rib",
        lambda *args, **kwargs: RibFeature(*args, **kwargs)  # type: ignore[arg-type]
    )
    FeatureRegistry.register(
        "HelixFeature", "Hélice 3D (Ressort / Vis)", FeatureCategory.SKETCH_BASED,
        "Génère un ressort hélicoïdal ou un pas de vis", "helix",
        lambda *args, **kwargs: HelixFeature(*args, **kwargs)  # type: ignore[arg-type]
    )

    # Modifications volumiques
    FeatureRegistry.register(
        "HoleFeature", "Perçage / Alésage", FeatureCategory.MODIFICATION,
        "Perce avec lamage (CHC) ou fraisage (FHC)", "hole",
        lambda *args, **kwargs: HoleFeature(*args, **kwargs)  # type: ignore[arg-type]
    )
    FeatureRegistry.register(
        "PocketFeature", "Poche / Cavité", FeatureCategory.MODIFICATION,
        "Creuse une poche dans une pièce", "pocket",
        lambda *args, **kwargs: PocketFeature(*args, **kwargs)  # type: ignore[arg-type]
    )
    FeatureRegistry.register(
        "ShellFeature", "Coque Évidée (Shell)", FeatureCategory.MODIFICATION,
        "Évide l'intérieur pour obtenir une paroi constante", "shell",
        lambda *args, **kwargs: ShellFeature(*args, **kwargs)  # type: ignore[arg-type]
    )
    FeatureRegistry.register(
        "FilletFeature", "Congé / Raccord (Fillet)", FeatureCategory.MODIFICATION,
        "Arrondit les arêtes vives", "fillet",
        lambda *args, **kwargs: FilletFeature(*args, **kwargs)  # type: ignore[arg-type]
    )
    FeatureRegistry.register(
        "ChamferFeature", "Chanfrein (Chamfer)", FeatureCategory.MODIFICATION,
        "Biseaute les arêtes vives", "chamfer",
        lambda *args, **kwargs: ChamferFeature(*args, **kwargs)  # type: ignore[arg-type]
    )
    FeatureRegistry.register(
        "DraftFeature", "Dépouille de Démoulage", FeatureCategory.MODIFICATION,
        "Incline les faces latérales pour moules d'injection", "draft",
        lambda *args, **kwargs: DraftFeature(*args, **kwargs)  # type: ignore[arg-type]
    )
    FeatureRegistry.register(
        "SplitFeature", "Découpe / Partitionnement", FeatureCategory.MODIFICATION,
        "Scinde un corps selon un plan de coupe", "split",
        lambda *args, **kwargs: SplitFeature(*args, **kwargs)  # type: ignore[arg-type]
    )
    FeatureRegistry.register(
        "BooleanFeature", "Opération Booléenne", FeatureCategory.MODIFICATION,
        "Union, Différence ou Intersection de deux corps", "boolean",
        lambda *args, **kwargs: BooleanFeature(*args, **kwargs)  # type: ignore[arg-type]
    )

    # Répétitions
    FeatureRegistry.register(
        "LinearPatternFeature", "Répétition Linéaire", FeatureCategory.PATTERN,
        "Matrice rectangulaire d'occurrences", "pattern_linear",
        lambda *args, **kwargs: LinearPatternFeature(*args, **kwargs)  # type: ignore[arg-type]
    )
    FeatureRegistry.register(
        "CircularPatternFeature", "Répétition Circulaire", FeatureCategory.PATTERN,
        "Répétition polaire autour de l'axe", "pattern_circular",
        lambda *args, **kwargs: CircularPatternFeature(*args, **kwargs)  # type: ignore[arg-type]
    )
    FeatureRegistry.register(
        "MirrorFeature", "Symétrie Miroir", FeatureCategory.PATTERN,
        "Symétrie par rapport à un plan cartésien", "mirror",
        lambda *args, **kwargs: MirrorFeature(*args, **kwargs)  # type: ignore[arg-type]
    )

    # Métiers spécialisés
    FeatureRegistry.register(
        "SheetMetalFeature", "Tôlerie Pliée", FeatureCategory.SHEET_METAL,
        "Tôle paramétrique avec K-factor et dépliage", "sheetmetal",
        lambda *args, **kwargs: SheetMetalFeature(*args, **kwargs)  # type: ignore[arg-type]
    )
    FeatureRegistry.register(
        "FastenerFeature", "Visserie Normalisée", FeatureCategory.HARDWARE,
        "Boulons, vis et écrous ISO métriques", "bolt",
        lambda *args, **kwargs: FastenerFeature(*args, **kwargs)  # type: ignore[arg-type]
    )


# Initialisation automatique au chargement du module
bootstrap_default_features()
