"""
Suite de tests unitaires pour l'intégration ECAD Gerber RS-274X, KiCad PCB et Solveur Thermique 2D.
"""

from __future__ import annotations
import pytest
import numpy as np

from src.specialized.pcb_integrator import (
    RS274XParser, KiCadPCBParser, PCBBoard, PCBComponent3D,
    verify_enclosure_clearance, verify_component_clearance_matrix
)
from src.specialized.ecad_thermal_twin import CopperTrace, SMTComponent, ECADThermalTwin


def test_gerber_rs274x_apertures_and_traces() -> None:
    """Vérifie le parsing des apertures, coordonnées et tracés RS-274X."""
    gerber_data = """
    %FSLAX25Y25*%
    %MOMM*%
    %ADD10C,0.300000*%
    %ADD11R,1.500000X0.800000*%
    D10*
    X1000000Y1000000D02*
    X4000000Y1000000D01*
    X4000000Y3000000D01*
    D11*
    X4000000Y3000000D03*
    M02*
    """
    parser = RS274XParser()
    res = parser.parse_string(gerber_data, layer_name="F.Cu")

    assert len(res.traces) == 2
    assert len(res.flashes) == 1
    assert pytest.approx(res.traces[0].width_mm, 1e-3) == 0.3
    assert pytest.approx(res.traces[0].start_x, 1e-3) == 10.0
    assert pytest.approx(res.traces[0].end_x, 1e-3) == 40.0
    assert res.flashes[0].shape == "R"


def test_gerber_board_instantiation_and_thermal_twin() -> None:
    """Vérifie l'instanciation de PCBBoard depuis Gerber et le calcul thermique."""
    outline_gerber = """
    %FSLAX25Y25*%
    %MOMM*%
    %ADD10C,0.150000*%
    D10*
    X0Y0D02*
    X8000000Y0D01*
    X8000000Y6000000D01*
    X0Y6000000D01*
    X0Y0D01*
    M02*
    """
    copper_gerber = """
    %FSLAX25Y25*%
    %MOMM*%
    %ADD10C,0.800000*%
    D10*
    X1000000Y1000000D02*
    X6000000Y1000000D01*
    M02*
    """
    board = PCBBoard.from_gerber(outline_gerber, copper_gerber=copper_gerber, name="PowerSupply")
    assert board.width_mm == pytest.approx(80.0, rel=1e-2)
    assert board.height_mm == pytest.approx(60.0, rel=1e-2)
    assert len(board.traces) == 1

    board.add_component(PCBComponent3D(
        designator="Q1",
        package="DPAK",
        pos_x=30.0,
        pos_y=20.0,
        width_x=10.0,
        length_y=10.0,
        height_z=4.0
    ))

    twin = board.create_thermal_twin(default_trace_current_amps=2.0)
    report = twin.solve_thermal_equilibrium(ambient_temp_c=25.0, grid_resolution=15, max_iterations=40)

    assert report.max_board_temp_c > 25.0
    assert report.temperature_grid.shape == (15, 15)
    assert report.copper_density_grid.shape == (15, 15)


def test_kicad_pcb_parsing() -> None:
    """Vérifie le parsing S-expression d'un fichier .kicad_pcb."""
    kicad_sample = """(kicad_pcb (version 20211014) (generator pcbnew)
      (general (thickness 1.6))
      (gr_line (start 0 0) (end 100 0) (layer "Edge.Cuts") (width 0.15))
      (gr_line (start 100 0) (end 100 80) (layer "Edge.Cuts") (width 0.15))
      (gr_line (start 100 80) (end 0 80) (layer "Edge.Cuts") (width 0.15))
      (gr_line (start 0 80) (end 0 0) (layer "Edge.Cuts") (width 0.15))
      (segment (start 10 10) (end 60 10) (width 0.8) (layer "F.Cu") (net 1))
      (footprint "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm"
        (layer "F.Cu")
        (at 40 30 0)
        (property "Reference" "U1")
      )
      (footprint "Resistor_SMD:R_0805_2012Metric"
        (layer "F.Cu")
        (at 70 20 0)
        (property "Reference" "R1")
      )
    )"""
    board = PCBBoard.from_kicad_pcb(kicad_sample, name="ControllerBoard")

    assert board.width_mm == pytest.approx(100.0, rel=1e-2)
    assert board.height_mm == pytest.approx(80.0, rel=1e-2)
    assert board.thickness_mm == pytest.approx(1.6, rel=1e-2)
    assert len(board.components) == 2
    assert len(board.traces) == 1
    assert board.components[0].ref_des == "U1"
    assert board.components[1].ref_des == "R1"
