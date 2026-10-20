"""Vérificateur et auditeur déterministe TechDraw GD&T et Tôlerie (v1.0).

Contrôle les cadres de tolérances géométriques (ASME Y14.5 / ISO 1101),
calcule l'allongement et la perte au pli (DIN 6935) et valide la cohérence des datums.
100% typage statique strict (zéro Any, zéro object), complexité cognitive <= 15.
"""

from dataclasses import dataclass
import math
import sys
from typing import Final, List, Optional, Set, Tuple


@dataclass(frozen=True)
class GDTFrameVerdict:
    """Résultat de validation d'un cadre de tolérance géométrique (FCF)."""

    symbol: str
    tolerance_value_mm: float
    datums: List[str]
    has_bonus_tolerance_mmc: bool
    is_datum_reference_valid: bool
    is_conforming: bool


@dataclass(frozen=True)
class SheetMetalBendResult:
    """Calcul d'allongement et de perte au pli pour tôle métallique."""

    thickness_mm: float
    bend_radius_mm: float
    bend_angle_deg: float
    k_factor: float
    bend_allowance_ba_mm: float
    bend_deduction_bd_mm: float
    is_physically_valid: bool


def calculate_sheet_metal_bend(
    thickness_mm: float,
    radius_mm: float,
    angle_deg: float,
    k_factor: float = 0.333,
) -> SheetMetalBendResult:
    """Calcule le Bend Allowance (BA) et le Bend Deduction (BD) selon DIN 6935."""
    if thickness_mm <= 0.0 or radius_mm <= 0.0 or angle_deg <= 0.0:
        return SheetMetalBendResult(
            thickness_mm=thickness_mm,
            bend_radius_mm=radius_mm,
            bend_angle_deg=angle_deg,
            k_factor=k_factor,
            bend_allowance_ba_mm=0.0,
            bend_deduction_bd_mm=0.0,
            is_physically_valid=False,
        )

    # Invariant physique : 0.20 <= K <= 0.50
    k_valid = (0.20 <= k_factor <= 0.50)

    theta_rad = math.radians(angle_deg)
    # BA = theta * (R + K * T)
    ba = theta_rad * (radius_mm + k_factor * thickness_mm)
    # Setback = (R + T) * tan(theta / 2)
    setback = (radius_mm + thickness_mm) * math.tan(theta_rad / 2.0)
    # BD = 2 * Setback - BA
    bd = 2.0 * setback - ba

    return SheetMetalBendResult(
        thickness_mm=thickness_mm,
        bend_radius_mm=radius_mm,
        bend_angle_deg=angle_deg,
        k_factor=k_factor,
        bend_allowance_ba_mm=ba,
        bend_deduction_bd_mm=bd,
        is_physically_valid=k_valid,
    )


def audit_gdt_feature_control_frame(
    symbol: str,
    tolerance_mm: float,
    datums: List[str],
    available_datums: Set[str],
    is_mmc: bool = False,
) -> GDTFrameVerdict:
    """Vérifie la syntaxe et la complétude d'un cadre de tolérance géométrique."""
    ALLOWED_SYMBOLS: Final[Set[str]] = {
        "FLATNESS",
        "STRAIGHTNESS",
        "CIRCULARITY",
        "CYLINDRICITY",
        "PERPENDICULARITY",
        "PARALLELISM",
        "ANGULARITY",
        "POSITION",
        "COAXIALITY",
        "SYMMETRY",
        "RUNOUT",
        "TOTAL_RUNOUT",
        "PROFILE_SURFACE",
        "PROFILE_LINE",
    }

    sym_valid = symbol.upper() in ALLOWED_SYMBOLS
    tol_valid = tolerance_mm > 0.0

    # Les tolérances de forme pure (planéité, circularité) n'ont pas de datum
    is_form_tolerance = symbol.upper() in ("FLATNESS", "STRAIGHTNESS", "CIRCULARITY", "CYLINDRICITY")
    datums_ok = True

    if is_form_tolerance:
        # Aucune référence datum requise
        datums_ok = (len(datums) == 0)
    else:
        # Nécessite au moins un datum primaire existant
        datums_ok = len(datums) > 0 and all(d in available_datums for d in datums)

    conforming = sym_valid and tol_valid and datums_ok

    return GDTFrameVerdict(
        symbol=symbol.upper(),
        tolerance_value_mm=tolerance_mm,
        datums=datums,
        has_bonus_tolerance_mmc=is_mmc,
        is_datum_reference_valid=datums_ok,
        is_conforming=conforming,
    )


def main() -> int:
    """Point d'entrée CLI pour la validation GD&T et tôlerie."""
    print("\n================ VÉRIFICATEUR TECHDRAW GD&T & TÔLERIE (SOTA 2026) ================")

    # 1. Test de pli de tôle acier 2.0 mm à 90 degrés
    bend = calculate_sheet_metal_bend(
        thickness_mm=2.0,
        radius_mm=3.0,
        angle_deg=90.0,
        k_factor=0.333,
    )
    print(f"Épaisseur tôle (T)     : {bend.thickness_mm:.1f} mm | Rayon pli (R) : {bend.bend_radius_mm:.1f} mm")
    print(f"Allongement au pli (BA): {bend.bend_allowance_ba_mm:.3f} mm")
    print(f"Perte au pli (BD)      : {bend.bend_deduction_bd_mm:.3f} mm")
    print(f"Validité physique K    : {'OUI (0.333 in [0.20, 0.50])' if bend.is_physically_valid else 'NON'}")

    # 2. Test de cadre GD&T de position vraie au MMC
    gdt = audit_gdt_feature_control_frame(
        symbol="POSITION",
        tolerance_mm=0.05,
        datums=["A", "B", "C"],
        available_datums={"A", "B", "C", "D"},
        is_mmc=True,
    )
    print(f"\nCadre GD&T Symbole     : {gdt.symbol}")
    print(f"Tolérance Position     : ± {gdt.tolerance_value_mm} mm (Modificateur MMC)")
    print(f"Datums de référence    : {gdt.datums}")
    print(f"Conformité ASME/ISO    : {'CONFORME' if gdt.is_conforming else 'REJETÉ'}\n")

    return 0 if (bend.is_physically_valid and gdt.is_conforming) else 1


if __name__ == "__main__":
    sys.exit(main())
