"""
Suite de tests complète pour la fluidité, l'asynchronisme et la stabilité IA dans CAD Studio :
- AICancellationToken & Watchdog
- CADTransactionManager & AtomicTransactionScope (Rollback sur erreur)
- BatchNotificationScope (Fluidité UI)
- SmartErrorDiagnostics (Auto-remédiation)
- CADAIAsyncExecutor (Exécution d'arrière-plan sans gel)
- Intégration CADAIBridge (Undo / Redo en langage naturel)
- Intégration CADScriptEngine (Protection contre les corruptions et boucles infinies)
- Intégration MCPStdioServer (Ping, annulation et gestion d'erreurs)
"""

from __future__ import annotations
import time
import pytest
from typing import Dict, List, Optional

from src.core.document import CADDocument
from src.core.geometry import make_box, make_cylinder, Solid
from src.ai.cad_ai_stability import (
    AICancellationToken,
    AICancelledException,
    AITimeoutException,
    CADTransactionSnapshot,
    CADTransactionManager,
    AtomicTransactionScope,
    BatchNotificationScope,
    DiagnosticCategory,
    DiagnosticResult,
    SmartErrorDiagnostics,
    TaskState,
    AITaskFuture,
    CADAIAsyncExecutor
)
from src.ai.cad_ai_bridge import CADAIBridge, AICommandType
from src.ai.cad_script_engine import CADScriptEngine
from src.ai.mcp_stdio import MCPStdioServer


# =========================================================================
# 1. Tests AICancellationToken & Watchdog
# =========================================================================

def test_cancellation_token_manual_cancel() -> None:
    token = AICancellationToken()
    assert token.is_cancelled() is False
    token.cancel("Interruption manuelle")
    assert token.is_cancelled() is True
    with pytest.raises(AICancelledException) as excinfo:
        token.check_cancelled()
    assert "Interruption manuelle" in str(excinfo.value)


def test_cancellation_token_timeout() -> None:
    token = AICancellationToken(timeout_seconds=0.05)
    time.sleep(0.08)
    assert token.is_cancelled() is True
    with pytest.raises(AITimeoutException) as excinfo:
        token.check_cancelled()
    assert "Délai d'exécution dépassé" in str(excinfo.value)


# =========================================================================
# 2. Tests CADTransactionManager & Rollback Atomique
# =========================================================================

def test_transaction_manager_snapshot_and_restore() -> None:
    doc = CADDocument("Doc Test")
    doc.bodies["Box1"] = make_box(20, 20, 20)

    snap = CADTransactionManager.capture_snapshot(doc, "Initial")
    assert "Box1" in snap.bodies

    # Modifie le document
    doc.bodies["Box2"] = make_box(10, 10, 10)
    del doc.bodies["Box1"]
    assert "Box2" in doc.bodies
    assert "Box1" not in doc.bodies

    # Restaure l'état
    CADTransactionManager.restore_snapshot(doc, snap)
    assert "Box1" in doc.bodies
    assert "Box2" not in doc.bodies


def test_atomic_transaction_scope_rollback_on_exception() -> None:
    doc = CADDocument("Test Atomic Scope")
    doc.bodies["Piece_Initial"] = make_box(50, 50, 10)
    assert len(doc.bodies) == 1

    try:
        with AtomicTransactionScope(doc, "Opération risquée"):
            doc.bodies["Piece_Temp_1"] = make_box(10, 10, 10)
            doc.bodies["Piece_Temp_2"] = make_box(20, 20, 20)
            assert len(doc.bodies) == 3
            # Simule une erreur de modélisation ou exception
            raise ValueError("Erreur géométrique simulée")
    except ValueError:
        pass

    # Vérifie le rollback intégral : les corps temporaires ont disparu
    assert len(doc.bodies) == 1
    assert "Piece_Initial" in doc.bodies
    assert "Piece_Temp_1" not in doc.bodies
    assert "Piece_Temp_2" not in doc.bodies


def test_atomic_transaction_scope_success_commit() -> None:
    doc = CADDocument("Test Atomic Success")
    CADTransactionManager.clear_history()

    with AtomicTransactionScope(doc, "Ajout Boîte"):
        doc.bodies["Piece_A"] = make_box(30, 30, 10)

    assert "Piece_A" in doc.bodies
    # Test undo
    ok_undo, _ = CADTransactionManager.undo(doc)
    assert ok_undo is True
    assert "Piece_A" not in doc.bodies

    # Test redo
    ok_redo, _ = CADTransactionManager.redo(doc)
    assert ok_redo is True
    assert "Piece_A" in doc.bodies


# =========================================================================
# 3. Tests BatchNotificationScope (Fluidité UI)
# =========================================================================

def test_batch_notification_scope_suppresses_callbacks() -> None:
    doc = CADDocument("Test Batch")
    call_count = 0

    def listener() -> None:
        nonlocal call_count
        call_count += 1

    doc.register_change_listener(listener)

    with BatchNotificationScope(doc):
        for i in range(10):
            doc.bodies[f"Piece_{i}"] = make_box(5, 5, 5)
            doc._notify_change()

    # Durant la boucle de 10 étapes, aucune notification n'a été reçue
    # À la sortie du with, exactement 1 notification globale consolidée a été tirée
    assert call_count == 1
    assert len(doc.bodies) == 10


# =========================================================================
# 4. Tests SmartErrorDiagnostics (Auto-Remédiation)
# =========================================================================

def test_smart_error_diagnostics_categories() -> None:
    err_syntax = SyntaxError("invalid syntax")
    diag_syntax = SmartErrorDiagnostics.diagnose(err_syntax)
    assert diag_syntax.category == DiagnosticCategory.SYNTAX_ERROR
    assert len(diag_syntax.remediation_hint) > 0

    err_timeout = AITimeoutException("Délai d'exécution dépassé (10.0s)")
    diag_timeout = SmartErrorDiagnostics.diagnose(err_timeout)
    assert diag_timeout.category == DiagnosticCategory.TIMEOUT_ERROR

    err_empty = ValueError("Solide vide (empty solid)")
    diag_empty = SmartErrorDiagnostics.diagnose(err_empty)
    assert diag_empty.category == DiagnosticCategory.EMPTY_SOLID

    err_wall = ValueError("L'épaisseur de paroi (wall thickness) dépasse la géométrie")
    diag_wall = SmartErrorDiagnostics.diagnose(err_wall)
    assert diag_wall.category == DiagnosticCategory.PARAM_OUT_OF_BOUNDS


# =========================================================================
# 5. Tests CADAIAsyncExecutor (Fluidité 60 FPS)
# =========================================================================

def test_async_executor_execution_and_progress() -> None:
    def heavy_job(token: AICancellationToken, update_prog: Callable[[float, str], None]) -> Dict[str, str]:
        update_prog(25.0, "Initialisation")
        time.sleep(0.02)
        token.check_cancelled()
        update_prog(75.0, "Calcul FEA")
        time.sleep(0.02)
        update_prog(100.0, "Succès")
        return {"status": "ok", "elements": "500"}

    future = CADAIAsyncExecutor.submit("TestJob", heavy_job, timeout_seconds=5.0)
    assert future.task_name == "TestJob"

    # Attente asynchrone non bloquante
    res_done = future.wait(timeout_s=2.0)
    assert res_done is True
    assert future.state == TaskState.COMPLETED
    assert future.progress_percent == 100.0

    raw_res = future.get_result()
    assert isinstance(raw_res, dict)
    assert raw_res.get("status") == "ok"


def test_async_executor_cancellation() -> None:
    def cancellable_job(token: AICancellationToken, update_prog: Callable[[float, str], None]) -> Dict[str, str]:
        for i in range(20):
            token.check_cancelled()
            time.sleep(0.02)
        return {"status": "finished"}

    future = CADAIAsyncExecutor.submit("CancelJob", cancellable_job, timeout_seconds=5.0)
    time.sleep(0.03)
    future.cancel("Annulé expressément")
    future.wait(timeout_s=2.0)

    assert future.state == TaskState.CANCELLED


# =========================================================================
# 6. Tests Intégration CADAIBridge (Undo/Redo & Rollback)
# =========================================================================

def test_bridge_natural_language_undo_redo() -> None:
    doc = CADDocument("Bridge Stability Doc")
    bridge = CADAIBridge(doc)

    # 1. Crée un cube
    res_create = bridge.execute_prompt("Crée un cube de 40x40x20")
    assert res_create.success is True
    assert len(doc.bodies) == 1

    # 2. Annule via prompt en français
    res_undo = bridge.execute_prompt("annule la dernière commande")
    assert res_undo.success is True
    assert res_undo.command_type == AICommandType.UNDO
    assert len(doc.bodies) == 0

    # 3. Rétablit via prompt
    res_redo = bridge.execute_prompt("rétablis")
    assert res_redo.success is True
    assert res_redo.command_type == AICommandType.REDO
    assert len(doc.bodies) == 1


# =========================================================================
# 7. Tests Intégration CADScriptEngine (Protection contre corruptions)
# =========================================================================

def test_script_engine_rollback_on_partial_failure() -> None:
    doc = CADDocument("Script Stability Doc")
    code_failing = """
b1 = cad.box(20, 20, 10)
cad.commit(b1, 'Part1')
# Provoque une division par zéro ou exception
x = 10 / 0
b2 = cad.box(10, 10, 10)
cad.commit(b2, 'Part2')
"""
    res = CADScriptEngine.execute_script(doc, code_failing)
    assert res.success is False
    assert "division by zero" in res.message
    # Le document ne doit PAS contenir Part1 : rollback atomique parfait !
    assert len(doc.bodies) == 0


def test_script_engine_watchdog_timeout() -> None:
    doc = CADDocument("Script Watchdog Doc")
    # Script rapide avec timeout très court (0.05s) et boucle créant des boîtes
    code_loop = """
for i in range(5000):
    b = cad.box(10, 10, 10)
"""
    res = CADScriptEngine.execute_script(doc, code_loop, timeout_seconds=0.01)
    assert res.success is False
    assert "Délai d'exécution dépassé" in res.message


def test_script_engine_watchdog_aborts_pure_infinite_loop() -> None:
    """Vérifie qu'une boucle infinie pure (while True: pass) ne gèle pas le thread et est interrompue par le watchdog."""
    doc = CADDocument("Script Infinite Loop Doc")
    code_infinite = """
x = 0
while True:
    x += 1
"""
    res = CADScriptEngine.execute_script(doc, code_infinite, timeout_seconds=0.05)
    assert res.success is False
    assert "Délai d'exécution dépassé" in res.message or "Timeout" in res.message


# =========================================================================
# 8. Tests Intégration MCPStdioServer (Ping & Cancel)
# =========================================================================

def test_mcp_stdio_ping_and_cancel() -> None:
    server = MCPStdioServer()

    # Ping
    ping_resp = server.process_request({"jsonrpc": "2.0", "id": "p-1", "method": "ping", "params": {}})
    assert ping_resp["id"] == "p-1"
    assert "result" in ping_resp

    # Cancel notification
    cancel_resp = server.process_request({
        "jsonrpc": "2.0",
        "method": "notifications/cancelled",
        "params": {"requestId": "tool-123"}
    })
    assert cancel_resp == {}
