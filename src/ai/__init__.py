"""
Package d'intelligence artificielle et d'automatisation cognitive (CAD Studio AI).
Fournit la passerelle déclarative et le synthétiseur de formes pour les agents et LLMs.
"""

from src.ai.shape_synthesizer import ShapeSynthesizer
from src.ai.cad_ai_bridge import CADAIBridge, CADAIExecutionResult, AICommandType

__all__ = [
    "ShapeSynthesizer",
    "CADAIBridge",
    "CADAIExecutionResult",
    "AICommandType"
]
