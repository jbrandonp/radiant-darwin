# CAD Studio (Parametric 3D CAD Suite)

A high-performance parametric 3D CAD modeling software inspired by **Autodesk Fusion 360** and **FreeCAD**.

Built with **PySide6 (Qt6)**, **OpenGL**, and the **Manifold3D** geometric kernel for watertight, robust CSG and B-Rep modeling with real-time viewport feedback and parametric history tracking.

---

## 🌟 Key Features

1. **Autodesk Fusion 360 Style UI**:
   - **Top Ribbon Bar**: Organized into **SOLID**, **SKETCH**, **MODIFY**, and **EXPORT** workbenches.
   - **Model Browser (Left)**: Complete project tree including Origin axes ($X, Y, Z$), Origin planes ($XY, XZ, YZ$), 3D Solid Bodies, and 2D Sketches.
   - **Parametric History Timeline (Bottom)**: Chronological step-by-step history bar with interactive playback controls ($\text{First}, \text{Prev}, \text{Play}, \text{Next}, \text{Last}$) and rollback functionality.
   - **Parameters Inspector (Right)**: Real-time dynamic editing of feature dimensions (width, height, depth, radius, extrusion distance) with instant 3D model recalculation.

2. **3D Interactive Viewport**:
   - Hardware-accelerated **OpenGL** rendering with smooth Phong shading and realistic ambient/directional lighting.
   - **CAD Outlines**: Distinctive crisp dark silhouette and sharp edge overlay for authentic CAD aesthetics.
   - **Ground Reference Grid**: Cartesian coordinate grid with colored primary axes ($X=\text{Red}, Y=\text{Green}, Z=\text{Blue}$).
   - **ViewCube Overlay**: Fast preset viewpoint navigation (Top, Front, Right, Bottom, Left, Isometric Home).
   - **Mouse Navigation**:
     - **Orbit**: Middle-click drag (or Right-click drag).
     - **Pan**: `Shift` + Middle-click drag.
     - **Zoom**: Mouse wheel scroll.
     - `F`: Fit all geometry to viewport.
     - `H`: Reset to Isometric Home view.

3. **Solid Geometry & 2D Sketch Engine**:
   - 3D Primitives: **Box**, **Cylinder**, **Sphere**, **Cone**.
   - 2D Sketching: Rectangles, Circles, Polygons on $XY$, $XZ$, and $YZ$ planes.
   - Operations: **Extrude** from 2D sketches to 3D solids.
   - CSG Booleans: **New Body**, **Join (Union)**, **Cut (Difference)**, **Intersect**.

4. **Manufacturing & 3D Printing Exporters**:
   - Direct export to **STL** (binary, ready for slicers: Cura, PrusaSlicer, Bambu Studio).
   - Export to **Wavefront OBJ** with vertex normals.
   - Export to **Stanford PLY**.

---

## 🚀 Getting Started

### Prerequisites
- Python 3.10+ (Windows, macOS, or Linux)

### Installation
```bash
# Clone the repository
git clone https://github.com/jbrandonp/radiant-darwin.git
cd radiant-darwin

# Create virtual environment
python -m venv .venv
.\.venv\Scripts\activate   # On Windows
# source .venv/bin/activate  # On Linux/macOS

# Install dependencies
pip install -r requirements.txt
```

### Running the Application
```bash
python src/main.py
```

### Running Unit Tests & Coverage
```bash
coverage run -m pytest tests/ -v -p no:cov
coverage report --include="src/core/*,src/viewport/camera.py"
```

---

## 📐 Architecture

```
src/
├── core/                  # Core parametric CAD engine
│   ├── types.py           # Strongly typed primitives (Vector3D, MeshBuffer, Enums)
│   ├── geometry.py        # Manifold3D volumetric kernel & CSG boolean engine
│   ├── sketch.py          # 2D parametric sketching engine
│   ├── feature.py         # Parametric feature graph (Box, Cylinder, Extrude, Combine)
│   ├── document.py        # History timeline, DAG re-evaluation, rollback controller
│   └── exporter.py        # 3D export pipeline (STL, OBJ, PLY)
├── viewport/              # 3D visualization and rendering
│   ├── camera.py          # Orbit/Pan/Zoom CAD camera controller
│   ├── gl_renderer.py     # OpenGL shaded rendering, edge outlines, ground grid
│   ├── view_cube.py       # Interactive ViewCube overlay widget
│   └── viewport_widget.py # QOpenGLWidget CAD viewport
├── ui/                    # Fusion 360-style user interface
│   ├── theme.py           # Fusion Dark QSS stylesheet
│   ├── ribbon.py          # Top Ribbon toolbar
│   ├── browser_tree.py    # Left model hierarchy tree
│   ├── timeline.py        # Bottom history timeline with playback controls
│   ├── properties_panel.py# Right live parameter inspector
│   ├── dialogs.py         # Feature creation dialog modals
│   └── main_window.py     # Main window assembly
└── main.py                # Application entry point
```
