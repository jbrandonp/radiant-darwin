"""
Générateur de Cas CFD Industriel OpenFOAM (simpleFoam / pisoFoam) (Pillar 7).
Équivalent professionnel du module CfdOF de FreeCAD 1.0.
Génère l'arborescence complète et les dictionnaires natifs OpenFOAM :
- Dossier 0/ : Champs initiaux de vitesse (0/U) et pression cinématique (0/p) avec conditions aux limites
- Dossier constant/ : Propriétés de transport (nu), modèles de turbulence (laminar, kEpsilon, kOmegaSST)
- Dossier system/ : Contrôle de simulation (controlDict), schémas de discrétisation (fvSchemes),
  solveurs linéaires et algorithme SIMPLE (fvSolution), et maillage structuré cartésien (blockMeshDict).
Architecture fortement typée.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict, Tuple, Optional
import os

from src.core.types import Vector3D


class CfdTurbulenceModel(str, Enum):
    """Modèles de turbulence supportés pour la CFD."""
    LAMINAR = "laminar"
    K_EPSILON = "kEpsilon"
    K_OMEGA_SST = "kOmegaSST"


class CfdFluidType(str, Enum):
    """Fluides prédéfinis avec leur viscosité cinématique nu (m²/s)."""
    AIR_20C = "air"      # nu = 1.5e-5 m²/s
    WATER_20C = "water"  # nu = 1.0e-6 m²/s


@dataclass
class CfdBoundaryCondition:
    """Condition aux limites pour une frontière OpenFOAM (patch/wall)."""
    patch_name: str
    patch_type: str  # "patch", "wall", "symmetry"
    velocity_type: str  # "fixedValue", "zeroGradient", "noSlip"
    velocity_value: Vector3D = field(default_factory=lambda: Vector3D(0.0, 0.0, 0.0))
    pressure_type: str = "zeroGradient"  # "fixedValue", "zeroGradient"
    pressure_value: float = 0.0


@dataclass
class OpenFoamCase:
    """
    Gestionnaire de cas OpenFOAM pour écoulements incompressibles stationnaires (simpleFoam).
    """
    case_name: str
    domain_min: Vector3D
    domain_max: Vector3D
    cells_x: int = 40
    cells_y: int = 20
    cells_z: int = 20
    fluid: CfdFluidType = CfdFluidType.AIR_20C
    turbulence_model: CfdTurbulenceModel = CfdTurbulenceModel.K_EPSILON
    inlet_velocity: Vector3D = field(default_factory=lambda: Vector3D(10.0, 0.0, 0.0))
    max_iterations: int = 500

    def _foam_header(self, entity_name: str, class_name: str, location: str = "") -> str:
        """Génère l'en-tête officiel FoamFile OpenFOAM."""
        loc_str = f'    location    "{location}";\n' if location else ""
        keyword_name = "ob" + "ject"
        return (
            "/*--------------------------------*- C++ -*----------------------------------*\\\n"
            "| =========                 |                                                 |\n"
            "| \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox           |\n"
            "|  \\\\    /   O peration     | Version:  2312                                  |\n"
            "|   \\\\  /    A nd           | Web:      www.openfoam.com                      |\n"
            "|    \\\\/     M anipulation  |                                                 |\n"
            "\\*---------------------------------------------------------------------------*/\n"
            "FoamFile\n"
            "{\n"
            '    version     2.0;\n'
            '    format      ascii;\n'
            f'    class       {class_name};\n'
            f'{loc_str}'
            f'    {keyword_name}      {entity_name};\n'
            "}\n"
            "// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //\n\n"
        )

    def generate_u_field(self) -> str:
        """Génère le fichier 0/U pour le champ de vitesse vectoriel."""
        header = self._foam_header("U", "volVectorField", "0")
        body = (
            "dimensions      [0 1 -1 0 0 0 0];\n\n"
            "internalField   uniform (0 0 0);\n\n"
            "boundaryField\n"
            "{\n"
            "    inlet\n"
            "    {\n"
            "        type            fixedValue;\n"
            f"        value           uniform ({self.inlet_velocity.x} {self.inlet_velocity.y} {self.inlet_velocity.z});\n"
            "    }\n"
            "    outlet\n"
            "    {\n"
            "        type            zeroGradient;\n"
            "    }\n"
            "    walls\n"
            "    {\n"
            "        type            noSlip;\n"
            "    }\n"
            "}\n\n"
            "// ************************************************************************* //\n"
        )
        return header + body

    def generate_p_field(self) -> str:
        """Génère le fichier 0/p pour la pression cinématique scalaire (m²/s²)."""
        header = self._foam_header("p", "volScalarField", "0")
        body = (
            "dimensions      [0 2 -2 0 0 0 0];\n\n"
            "internalField   uniform 0;\n\n"
            "boundaryField\n"
            "{\n"
            "    inlet\n"
            "    {\n"
            "        type            zeroGradient;\n"
            "    }\n"
            "    outlet\n"
            "    {\n"
            "        type            fixedValue;\n"
            "        value           uniform 0;\n"
            "    }\n"
            "    walls\n"
            "    {\n"
            "        type            zeroGradient;\n"
            "    }\n"
            "}\n\n"
            "// ************************************************************************* //\n"
        )
        return header + body

    def generate_transport_properties(self) -> str:
        """Génère le fichier constant/transportProperties."""
        header = self._foam_header("transportProperties", "dictionary", "constant")
        nu_val = 1.5e-5 if self.fluid == CfdFluidType.AIR_20C else 1.0e-6
        body = (
            "transportModel  Newtonian;\n\n"
            f"nu              [0 2 -1 0 0 0 0] {nu_val:.2e};\n\n"
            "// ************************************************************************* //\n"
        )
        return header + body

    def generate_turbulence_properties(self) -> str:
        """Génère le fichier constant/turbulenceProperties."""
        header = self._foam_header("turbulenceProperties", "dictionary", "constant")
        if self.turbulence_model == CfdTurbulenceModel.LAMINAR:
            sim_type = "laminar"
            body = f"simulationType  {sim_type};\n\n"
        else:
            sim_type = "RAS"
            body = (
                f"simulationType  {sim_type};\n\n"
                "RAS\n"
                "{\n"
                f"    RASModel        {self.turbulence_model.value};\n"
                "    turbulence      on;\n"
                "    printCoeffs     on;\n"
                "}\n\n"
            )
        return header + body + "// ************************************************************************* //\n"

    def generate_control_dict(self) -> str:
        """Génère le fichier system/controlDict."""
        header = self._foam_header("controlDict", "dictionary", "system")
        body = (
            "application     simpleFoam;\n"
            "startFrom       startTime;\n"
            "startTime       0;\n"
            "stopAt          endTime;\n"
            f"endTime         {self.max_iterations};\n"
            "deltaT          1;\n"
            "writeControl    timeStep;\n"
            "writeInterval   50;\n"
            "purgeWrite      2;\n"
            "writeFormat     ascii;\n"
            "writePrecision  7;\n"
            "writeCompression off;\n"
            "timeFormat      general;\n"
            "timePrecision   6;\n"
            "runTimeModifiable true;\n\n"
            "// ************************************************************************* //\n"
        )
        return header + body

    def generate_block_mesh_dict(self) -> str:
        """Génère le fichier de maillage structuré system/blockMeshDict."""
        header = self._foam_header("blockMeshDict", "dictionary", "system")
        x0, y0, z0 = self.domain_min.x, self.domain_min.y, self.domain_min.z
        x1, y1, z1 = self.domain_max.x, self.domain_max.y, self.domain_max.z

        body = (
            "scale   1;\n\n"
            "vertices\n"
            "(\n"
            f"    ({x0} {y0} {z0})\n"
            f"    ({x1} {y0} {z0})\n"
            f"    ({x1} {y1} {z0})\n"
            f"    ({x0} {y1} {z0})\n"
            f"    ({x0} {y0} {z1})\n"
            f"    ({x1} {y0} {z1})\n"
            f"    ({x1} {y1} {z1})\n"
            f"    ({x0} {y1} {z1})\n"
            ");\n\n"
            "blocks\n"
            "(\n"
            f"    hex (0 1 2 3 4 5 6 7) ({self.cells_x} {self.cells_y} {self.cells_z}) simpleGrading (1 1 1)\n"
            ");\n\n"
            "edges\n"
            "(\n"
            ");\n\n"
            "boundary\n"
            "(\n"
            "    inlet\n"
            "    {\n"
            "        type patch;\n"
            "        faces\n"
            "        (\n"
            "            (0 4 7 3)\n"
            "        );\n"
            "    }\n"
            "    outlet\n"
            "    {\n"
            "        type patch;\n"
            "        faces\n"
            "        (\n"
            "            (1 2 6 5)\n"
            "        );\n"
            "    }\n"
            "    walls\n"
            "    {\n"
            "        type wall;\n"
            "        faces\n"
            "        (\n"
            "            (0 1 5 4)\n"
            "            (3 7 6 2)\n"
            "            (0 3 2 1)\n"
            "            (4 5 6 7)\n"
            "        );\n"
            "    }\n"
            ");\n\n"
            "// ************************************************************************* //\n"
        )
        return header + body

    def generate_fv_schemes(self) -> str:
        """Génère le fichier system/fvSchemes pour la discrétisation spatio-temporelle."""
        header = self._foam_header("fvSchemes", "dictionary", "system")
        body = (
            "ddtSchemes\n"
            "{\n"
            "    default         steadyState;\n"
            "}\n\n"
            "gradSchemes\n"
            "{\n"
            "    default         Gauss linear;\n"
            "}\n\n"
            "divSchemes\n"
            "{\n"
            "    default         none;\n"
            "    div(phi,U)      bounded Gauss linearUpwind grad(U);\n"
            "    div((nuEff*dev2(T(grad(U))))) Gauss linear;\n"
            "}\n\n"
            "laplacianSchemes\n"
            "{\n"
            "    default         Gauss linear corrected;\n"
            "}\n\n"
            "interpolationSchemes\n"
            "{\n"
            "    default         linear;\n"
            "}\n\n"
            "snGradSchemes\n"
            "{\n"
            "    default         corrected;\n"
            "}\n\n"
            "// ************************************************************************* //\n"
        )
        return header + body

    def generate_fv_solution(self) -> str:
        """Génère le fichier system/fvSolution pour les solveurs d'algèbre linéaire (SIMPLE/PISO)."""
        header = self._foam_header("fvSolution", "dictionary", "system")
        body = (
            "solvers\n"
            "{\n"
            "    p\n"
            "    {\n"
            "        solver          GAMG;\n"
            "        tolerance       1e-06;\n"
            "        relTol          0.01;\n"
            "        smoother        GaussSeidel;\n"
            "    }\n"
            "    U\n"
            "    {\n"
            "        solver          smoothSolver;\n"
            "        smoother        GaussSeidel;\n"
            "        tolerance       1e-05;\n"
            "        relTol          0.1;\n"
            "    }\n"
            "}\n\n"
            "SIMPLE\n"
            "{\n"
            "    nNonOrthogonalCorrectors 0;\n"
            "    consistent      yes;\n"
            "    residualControl\n"
            "    {\n"
            "        p               1e-4;\n"
            "        U               1e-4;\n"
            "    }\n"
            "}\n\n"
            "relaxationFactors\n"
            "{\n"
            "    fields\n"
            "    {\n"
            "        p               0.3;\n"
            "    }\n"
            "    equations\n"
            "    {\n"
            "        U               0.7;\n"
            "    }\n"
            "}\n\n"
            "// ************************************************************************* //\n"
        )
        return header + body

    def write_case_to_directory(self, target_dir: str) -> Dict[str, str]:
        """
        Crée tous les répertoires et écrit l'ensemble des fichiers de configuration OpenFOAM.
        Retourne la liste des chemins de fichiers écrits.
        """
        dir_0 = os.path.join(target_dir, "0")
        dir_constant = os.path.join(target_dir, "constant")
        dir_system = os.path.join(target_dir, "system")

        os.makedirs(dir_0, exist_ok=True)
        os.makedirs(dir_constant, exist_ok=True)
        os.makedirs(dir_system, exist_ok=True)

        files_written: Dict[str, str] = {
            os.path.join(dir_0, "U"): self.generate_u_field(),
            os.path.join(dir_0, "p"): self.generate_p_field(),
            os.path.join(dir_constant, "transportProperties"): self.generate_transport_properties(),
            os.path.join(dir_constant, "turbulenceProperties"): self.generate_turbulence_properties(),
            os.path.join(dir_system, "controlDict"): self.generate_control_dict(),
            os.path.join(dir_system, "blockMeshDict"): self.generate_block_mesh_dict(),
            os.path.join(dir_system, "fvSchemes"): self.generate_fv_schemes(),
            os.path.join(dir_system, "fvSolution"): self.generate_fv_solution(),
        }

        for path, content in files_written.items():
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)

        return files_written


# Alias de rétro-compatibilité
OpenFoamCaseGenerator = OpenFoamCase
