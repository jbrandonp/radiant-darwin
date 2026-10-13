# CAD Studio (Industrial 3D CAD / FEA / CAM Suite)

A complete industrial-grade parametric 3D CAD suite inspired by **Autodesk Fusion 360** and **FreeCAD**.

Built with **PySide6 (Qt6)**, **OpenGL**, **Manifold3D**, and **SciPy**, integrating full mechanical design, geometric constraint solving, multi-component assemblies, FEA structural stress analysis, and CNC CAM G-code manufacturing.

---

## 🌟 Key Features & Workspaces

### 1. 🛠️ Solid Modeling & Features (Atelier Conception)
- **3D Primitives**: Parametric Box, Cylinder, Sphere, Cone.
- **Parametric Operations**:
  - **Extrude**: Linear extrusion from 2D sketch profiles.
  - **Revolve**: 360° or partial rotational revolution around central axis.
  - **Hole Tool**: Parametric counterbored/countersunk/plain cylindrical holes with depth and diameter controls.
  - **Shell**: Constant-thickness hollowing for enclosures and plastic injection molds.
  - **Linear & Circular Patterns**: Rectangular matrix and polar circular duplications.
  - **Mirror**: Planar symmetries across $XY$, $XZ$, and $YZ$ planes.
  - **Booleans (CSG)**: Join (Union), Cut (Difference), Intersect.
- **Bottom Timeline (Fusion 360 History)**:
  - Sequential chronological feature playback ($\text{First}, \text{Prev}, \text{Play}, \text{Next}, \text{Last}$).
  - Rollback slider bar to travel back in time and modify parent features.
- **Dynamic Parameters Inspector**: Real-time dimension editing with automatic DAG rebuild.

### 2. 📐 2D Sketcher & Geometric Constraint Solver (Atelier Esquisse)
- Non-linear constraint solver powered by **SciPy Trust Region Reflective (TRF)**.
- Constraints supported:
  - **Coincident**: Joins two points together ($u_a = u_b, v_a = v_b$).
  - **Horizontal & Vertical**: Segments constrained parallel to cartesian axes.
  - **Distance**: Dimension constraint between two points ($\Delta d = L$).
  - **Fixed Points**: Absolute coordinate locking.

### 3. 🧪 Physical Materials & Mass Properties
- Engineering material library:
  - **Aluminium 6061-T6**, **Stainless Steel 304**, **Carbon Steel C45**, **Titanium Ti-6Al-4V**, **Brass CuZn39Pb3**, **PLA**, **ABS**, **Carbon Fiber**.
- Automatic calculation of:
  - Exact part volume ($\text{mm}^3$ and $\text{cm}^3$).
  - Mass in grams and kilograms based on material density $\rho$.
  - 3D Center of Gravity (CoG) vector $(X, Y, Z)$.

### 4. 📊 Finite Element Analysis (Atelier Simulation FEA)
- Linear static structural elasticity analysis.
- Computes:
  - **von Mises equivalent stress** $\sigma_{vm}$ across nodes.
  - Maximum elastic displacement (deflection $\mu\text{m}$).
  - **Factor of Safety (FoS)** relative to material yield strength $\sigma_y$.
  - 3D rainbow colormap heatmap (Blue = $0\text{ MPa} \rightarrow$ Red = $\sigma_{\max}$).

### 5. ✂️ Computer-Aided Manufacturing (Atelier Fabrication CAM)
- **2.5D Toolpath Generation**:
  - **Facing (Surfaçage)**: Zigzag pocket clearing on top surface.
  - **2D Contour (Contournage)**: Multi-pass stepdown perimeter profiling.
- **CNC G-Code Post-Processor**:
  - Exports standard ISO G-Code compatible with **GRBL**, **Marlin**, **LinuxCNC**, and **Mach3**.
  - Configurable feed rates ($F$), spindle RPM ($S$), and safe clearance heights ($Z$).

### 6. 🔗 Assembly & Interference Detection (Atelier Assemblage)
- Kinematic mechanical joints: **Rigid**, **Revolute (Pivot)**, **Slider (Glissière)**, **Cylindrical**, **Ball (Rotule)**.
- Real-time kinematic joint animation.
- **Exact Interference Detection**: Exact CSG intersection volume check between mating components with zero-tolerance collision alerts.

### 7. 🖨️ 3D Manufacturing Exporters
- Binary **STL** (3D printing for Cura, Bambu Studio, PrusaSlicer).
- **Wavefront OBJ** with vertex normals.
- **Stanford PLY**.

---

## 🚀 Getting Started

### Installation
```bash
# Clone the repository
git clone https://github.com/jbrandonp/radiant-darwin.git
cd radiant-darwin

# Create virtual environment
python -m venv .venv
.\.venv\Scripts\activate   # Windows

# Install dependencies
pip install -r requirements.txt
```

### Running CAD Studio
```bash
python src/main.py
```

### Running Test Suite (100% Pass, 88% Coverage)
```bash
coverage run -m pytest tests/ -v -p no:cov
coverage report --include="src/core/*,src/materials/*,src/solver/*,src/cam/*,src/fea/*,src/assembly/*,src/viewport/camera.py"
```

---

## 🏛️ Project Structure

```
src/
├── core/                  # Parametric CAD engine (CSG, Manifold3D, DAG, History, Exporters)
├── solver/                # 2D non-linear geometric constraint solver (TRF)
├── materials/             # Engineering materials database and physical calculators
├── fea/                   # Finite Element Analysis (von Mises stresses, safety factor, colormap)
├── cam/                   # CAM toolpaths (Facing, Contour) & ISO/GRBL G-code post-processor
├── assembly/              # Kinematic joints & exact CSG interference/collision detection
├── viewport/              # Hardware-accelerated OpenGL viewport, ViewCube, CAD outlines, camera
├── ui/                    # Fusion 360 Dark QSS UI, Ribbon toolbar, Browser, Timeline, Inspector
└── main.py                # Main application entry point
```
