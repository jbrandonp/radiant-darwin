"""
Tests exhaustifs de l'importateur STEP B-Rep ISO 10303-21 (AP203, AP214, AP242).
Vérifie la reconstitution topologique formelle :
Vertex -> Edge -> Wire -> Face -> Shell -> BRep -> Solid étanche.
"""

import numpy as np
import pytest

from src.core.step_importer import STEPImporter, STEPGeometricContext, STEPModel
from src.core.nexus_kernel.brep_topology import SurfaceType, CurveType
from src.core.geometry import Solid


SAMPLE_STEP_CUBE = """ISO-10303-21;
HEADER;
FILE_DESCRIPTION(('STEP AP214 Model'), '2;1');
FILE_NAME('test_cube.stp', '2026-10-14T15:00:00', ('Author'), ('Org'), 'CAD Studio', '', '');
FILE_SCHEMA(('AUTOMOTIVE_DESIGN { 1 0 10303 214 1 1 1 1 }'));
ENDSEC;
DATA;
#10 = CARTESIAN_POINT('ORIGIN', (0.0, 0.0, 0.0));
#11 = CARTESIAN_POINT('P1', (20.0, 0.0, 0.0));
#12 = CARTESIAN_POINT('P2', (20.0, 20.0, 0.0));
#13 = CARTESIAN_POINT('P3', (0.0, 20.0, 0.0));
#14 = CARTESIAN_POINT('P4', (0.0, 0.0, 20.0));
#15 = CARTESIAN_POINT('P5', (20.0, 0.0, 20.0));
#16 = CARTESIAN_POINT('P6', (20.0, 20.0, 20.0));
#17 = CARTESIAN_POINT('P7', (0.0, 20.0, 20.0));

#20 = DIRECTION('DX', (1.0, 0.0, 0.0));
#21 = DIRECTION('DY', (0.0, 1.0, 0.0));
#22 = DIRECTION('DZ', (0.0, 0.0, 1.0));

#30 = AXIS2_PLACEMENT_3D('FRAME_BOTTOM', #10, #22, #20);
#31 = PLANE('PLANE_BOTTOM', #30);

#40 = VERTEX_POINT('V0', #10);
#41 = VERTEX_POINT('V1', #11);
#42 = VERTEX_POINT('V2', #12);
#43 = VERTEX_POINT('V3', #13);

#50 = EDGE_CURVE('E0', #40, #41, #20, .T.);
#51 = EDGE_CURVE('E1', #41, #42, #21, .T.);
#52 = EDGE_CURVE('E2', #42, #43, #20, .T.);
#53 = EDGE_CURVE('E3', #43, #40, #21, .T.);

#60 = POLY_LOOP('BOTTOM_LOOP', (#10, #11, #12, #13));
#61 = FACE_OUTER_BOUND('BOUND_BOTTOM', #60, .T.);
#70 = ADVANCED_FACE('FACE_BOTTOM', (#61), #31, .T.);

#80 = CLOSED_SHELL('OUTER_SHELL', (#70));
#90 = MANIFOLD_SOLID_BREP('CUBE_SOLID', #80);

#100 = DATUM_FEATURE('DATUM_PRIMARY', 'Reference Datum A');
#101 = GEOMETRIC_TOLERANCE('PERPENDICULARITY_TOL', 0.05, #100);
ENDSEC;
END-ISO-10303-21;
"""


def test_step_importer_records_and_context() -> None:
    """Vérifie l'analyse syntaxique des entités STEP et du schéma AP214."""
    importer = STEPImporter()
    context = importer.import_step(SAMPLE_STEP_CUBE)

    assert "214" in context.schema_name
    assert len(context.cartesian_points) == 8
    assert len(context.directions) == 3
    assert len(context.faces) == 1
    assert "CUBE_SOLID" in context.solids
    assert len(context.pmi_annotations) == 2


def test_step_importer_to_nexus_solid_topology() -> None:
    """Vérifie la reconstitution de la topologie B-Rep et la création de NexusSolid."""
    importer = STEPImporter()
    nexus_solid = importer.import_to_nexus_solid(SAMPLE_STEP_CUBE, solid_name="TestCube")

    assert nexus_solid.name == "TestCube"
    brep = nexus_solid.brep
    assert len(brep.vertices) >= 4
    assert len(brep.faces) >= 1
    face = list(brep.faces.values())[0]
    assert face.surface_type == SurfaceType.PLANE
    assert len(face.outer_wire.edges) >= 4

    # Le solide reconstruit possède un volume valide
    assert nexus_solid.volume() > 0.0
    assert nexus_solid.is_watertight() is True


def test_step_importer_to_cad_solid() -> None:
    """Vérifie la conversion directe en Solid éditable CAD Studio."""
    importer = STEPImporter()
    cad_solid = importer.import_to_cad_solid(SAMPLE_STEP_CUBE)

    assert isinstance(cad_solid, Solid)
    assert cad_solid.name == "CUBE_SOLID"
    assert cad_solid.volume() > 0.0
    b_min, b_max = cad_solid.bounding_box()
    assert b_max.x >= 20.0
    assert b_max.y >= 20.0
    assert b_max.z >= 20.0


def test_step_importer_import_model_with_metadata() -> None:
    """Vérifie le conteneur STEPModel avec métadonnées et PMI."""
    importer = STEPImporter()
    model: STEPModel = importer.import_model(SAMPLE_STEP_CUBE)

    assert model.schema_version != ""
    assert model.solid is not None
    assert len(model.pmi_annotations) == 2
    assert "DATUM_PRIMARY" in model.pmi_annotations[0]


def test_step_importer_modular_extractors() -> None:
    """Vérifie les extracteurs modulaires de repères, faces, solides et annotations PMI."""
    from src.core.step_importer import STEPRecord

    records = {
        10: STEPRecord(10, "AXIS2_PLACEMENT_3D", ["'Origin'", "#11", "#12"]),
        20: STEPRecord(20, "ADVANCED_FACE", ["'F1'", "#21", "#22"]),
        30: STEPRecord(30, "MANIFOLD_SOLID_BREP", ["'MainBody'", "#31"]),
        40: STEPRecord(40, "GEOMETRIC_TOLERANCE", ["'Tol1'", "0.05"]),
    }
    placements = STEPImporter._extract_axis_placements(records)
    faces = STEPImporter._extract_faces(records)
    solids = STEPImporter._extract_solids(records)
    pmi = STEPImporter._extract_pmi_annotations(records)

    assert 10 in placements
    assert 20 in faces
    assert "MainBody" in solids
    assert len(pmi) == 1
    assert "GEOMETRIC_TOLERANCE" in pmi[0]
