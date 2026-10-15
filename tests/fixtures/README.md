# CAD Test Fixtures — Radiant-Darwin

Ce répertoire contient des modèles CAO physiques réels normalisés pour tester les importateurs, exportateurs, maillages et passerelles d'ingénierie :

- `step/mechanical_bracket_ap214.step` : Modèle solide B-Rep conforme ISO 10303-21 STEP AP214 (50x30x15 mm, volume 22500 mm³).
- `step/precision_flange_ap242_pmi.step` : Modèle B-Rep avec annotations PMI et tolérancement GD&T conforme STEP AP242 (40x40x20 mm, volume 32000 mm³).
- `dxf/bracket_flat_pattern_r12.dxf` : Patron de tôlerie déplié conforme AutoCAD R12 ASCII (calques `CUT` et `BEND`).
- `dxf/laser_cut_gasket_2d.dxf` : Joint d'étanchéité 2D avec alésages de fixation et contour de découpe.
- `iges/benchmark_bracket_53.igs` : Archive CAO au format ANSI US-PRO IGES 5.3 avec structure stricte de cartes à 80 colonnes.
- `stl/calibration_cube_ascii.stl` : Cube de calibration étanche 20x20x20 mm ASCII (12 facettes triangulaires, volume 8000 mm³).
- `stl/benchmark_wedge_binary.stl` : Maillage solide binaire étanche (en-tête 80 octets, 12 triangles).
