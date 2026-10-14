"""
Package d'intelligence artificielle et d'automatisation cognitive (CAD Studio AI).
Fournit la passerelle déclarative et le synthétiseur de formes pour les agents et LLMs.
"""

from src.ai.shape_synthesizer import ShapeSynthesizer
from src.ai.cad_ai_bridge import CADAIBridge, CADAIExecutionResult, AICommandType
from src.ai.cad_validator import CADValidator, ValidationReport, InterferenceReport
from src.ai.cad_script_engine import CADScriptEngine, CADScriptContext, ScriptExecutionResult
from src.ai.mcp_schema import MCPToolRegistry, MCPToolDefinition
from src.ai.ai_vision_feedback import AIVisionFeedback, VisionFeedbackResult
from src.ai.ai_connector_config import AIConnectorConfigGenerator, AIClientConfigSnippet
from src.ai.mcp_stdio import MCPStdioServer

__all__ = [
    "ShapeSynthesizer",
    "CADAIBridge",
    "CADAIExecutionResult",
    "AICommandType",
    "CADValidator",
    "ValidationReport",
    "InterferenceReport",
    "CADScriptEngine",
    "CADScriptContext",
    "ScriptExecutionResult",
    "MCPToolRegistry",
    "MCPToolDefinition",
    "AIVisionFeedback",
    "VisionFeedbackResult",
    "AIConnectorConfigGenerator",
    "AIClientConfigSnippet",
    "MCPStdioServer",
]
