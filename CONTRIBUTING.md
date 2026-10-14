# Contributing to Radiant-Darwin (CAD Studio)

Thank you for your interest in contributing to **Radiant-Darwin**! We welcome pull requests, bug reports, and architectural proposals.

---

## 🛠️ Development Setup

1. **Clone the repository:**
   ```bash
   git clone https://github.com/jbrandonp/radiant-darwin.git
   cd radiant-darwin
   ```

2. **Create a virtual environment (Python 3.10+ required, 3.12 recommended):**
   ```bash
   python -m venv .venv
   # Windows:
   .\.venv\Scripts\activate
   # Linux/macOS:
   source .venv/bin/activate
   ```

3. **Install dependencies in editable development mode:**
   ```bash
   pip install -e ".[dev]"
   ```

---

## 🏛️ Code Standards & Architectural Rules

All pull requests must strictly satisfy the following requirements before being merged:

### 1. 100% Strict Static Typing (Zero `Any` / Zero `object`)
- **NEVER use `Any` or `object`** in `src/`.
- Every parameter, return type, and composite structure must be explicitly typed using strict dataclasses, TypedDicts, Protocols, or generic unions (e.g., `Union[int, float]`, `Optional[T]`).

### 2. Cognitive Complexity Ceiling ($\le 25$)
- No function or method may exceed a cognitive complexity score of **25**.
- Break complex algorithms down into focused, single-responsibility helper functions.

### 3. Conventional Commits
- Commit messages must follow the format: `type(scope): description`.
- Valid types: `feat`, `fix`, `refactor`, `docs`, `chore`, `test`, `perf`.
- Example: `feat(cam): add 5-axis collision avoidance heuristic`.

### 4. Deterministic Non-Regression Testing
- All existing tests (412+ tests) must pass.
- New features or bug fixes must include unit and integration tests under `tests/`.

---

## 🧪 Running Tests & Quality Verification

Run the full headless test suite:
```bash
# Set headless Qt offscreen platform
export QT_QPA_PLATFORM=offscreen # On Linux/macOS
# On Windows PowerShell: $env:QT_QPA_PLATFORM="offscreen"

pytest tests/ -v
```

Execute the deterministic industrial audit engine:
```bash
python scripts/industrial_audit_engine.py
```
*The build will only pass if the Quality Gate is 100% GREEN.*

---

## 📜 Code of Conduct

Be welcoming, professional, and respectful. For major changes, please open an issue first to discuss what you would like to change.
