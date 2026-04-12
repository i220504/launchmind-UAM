from __future__ import annotations

import json
import os
import time
from contextlib import contextmanager

from config import settings
from runtime.orchestrator import LaunchMindOrchestrator
from utils.logger import get_logger


def _pid_is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


@contextmanager
def _run_lock() -> None:
    lock_path = settings.run_lock_path
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    if lock_path.exists():
        try:
            payload = json.loads(lock_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            payload = {}
        existing_pid = int(payload.get("pid", 0) or 0)
        if existing_pid and _pid_is_running(existing_pid):
            raise RuntimeError(f"Another LaunchMind run is already active (pid={existing_pid}). Stop it before starting a new run.")
        lock_path.unlink(missing_ok=True)

    lock_path.write_text(
        json.dumps({"pid": os.getpid(), "started_at": time.time()}, indent=2),
        encoding="utf-8",
    )
    try:
        yield
    finally:
        lock_path.unlink(missing_ok=True)


def run_startup(startup_idea: str) -> dict:
    logger = get_logger("startup_runner")
    with _run_lock():
        orchestrator = LaunchMindOrchestrator()
        orchestrator.validate_integrations()
        orchestrator.start_agents()
        logger.info("Starting workflow for startup idea: %s", startup_idea)
        orchestrator.ceo.start_workflow(startup_idea)

        timeout_seconds = settings.workflow_timeout_seconds
        started = time.time()
        while not orchestrator.ceo.completed.wait(timeout=1):
            if time.time() - started > timeout_seconds:
                orchestrator.ceo.state["errors"].append(
                    {"failed_agent": "system", "error": f"Workflow timed out after {timeout_seconds} seconds"}
                )
                orchestrator.ceo._finalize(status="failed")
                break

        summary = orchestrator.ceo.state["final_summary"]
        logger.info("Workflow completed with status=%s", summary["status"])
        return summary
