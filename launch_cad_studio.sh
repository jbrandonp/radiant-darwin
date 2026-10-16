#!/usr/bin/env bash
# ==============================================================================
# CAD Studio 2026 (NEXUS-3D Enterprise) - Linux & macOS Launcher
# ==============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
export PYTHONPATH="$SCRIPT_DIR:${PYTHONPATH:-}"

echo "==================================================="
echo " CAD Studio 2026 (NEXUS-3D Enterprise) - Launcher"
echo "==================================================="

# Detect virtual environment
if [ -f ".venv/bin/python" ]; then
    echo "[INFO] Using local virtual environment (.venv)..."
    exec ".venv/bin/python" -m src.main "$@"
elif [ -f "venv/bin/python" ]; then
    echo "[INFO] Using local virtual environment (venv)..."
    exec "venv/bin/python" -m src.main "$@"
elif command -v uv &> /dev/null; then
    echo "[INFO] Using uv run..."
    exec uv run python -m src.main "$@"
else
    echo "[INFO] Using system python3..."
    exec python3 -m src.main "$@"
fi
