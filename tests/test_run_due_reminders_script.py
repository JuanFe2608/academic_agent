"""Tests del exit code de run_due_reminders.py."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock

from services.reminders.dispatcher import RunDueRemindersResult


def _load_script(name: str):
    script_path = Path(f"scripts/{name}.py")
    spec = importlib.util.spec_from_file_location(name, script_path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _runner_returning(result: RunDueRemindersResult) -> MagicMock:
    runner = MagicMock()
    runner.run_due_dispatches.return_value = result
    return runner


def test_main_exits_0_when_nothing_leased(monkeypatch) -> None:
    module = _load_script("run_due_reminders")
    result = RunDueRemindersResult(processed=True, leased_count=0, sent_count=0)
    monkeypatch.setattr(module, "build_reminder_dispatch_runner", lambda: _runner_returning(result))
    monkeypatch.setattr(sys, "argv", ["run_due_reminders.py"])
    assert module.main() == 0


def test_main_exits_0_when_some_sent(monkeypatch) -> None:
    module = _load_script("run_due_reminders")
    result = RunDueRemindersResult(processed=True, leased_count=3, sent_count=2, failed_count=1)
    monkeypatch.setattr(module, "build_reminder_dispatch_runner", lambda: _runner_returning(result))
    monkeypatch.setattr(sys, "argv", ["run_due_reminders.py"])
    assert module.main() == 0


def test_main_exits_1_on_infrastructure_error(monkeypatch) -> None:
    module = _load_script("run_due_reminders")
    result = RunDueRemindersResult(
        processed=False, error_code="db_error", detail="connection refused"
    )
    monkeypatch.setattr(module, "build_reminder_dispatch_runner", lambda: _runner_returning(result))
    monkeypatch.setattr(sys, "argv", ["run_due_reminders.py"])
    assert module.main() == 1


def test_main_exits_1_when_all_dispatches_fail(monkeypatch) -> None:
    module = _load_script("run_due_reminders")
    result = RunDueRemindersResult(
        processed=True, leased_count=3, sent_count=0, failed_count=3
    )
    monkeypatch.setattr(module, "build_reminder_dispatch_runner", lambda: _runner_returning(result))
    monkeypatch.setattr(sys, "argv", ["run_due_reminders.py"])
    assert module.main() == 1


def test_main_exits_1_when_all_retryable(monkeypatch) -> None:
    """Cero enviados aunque sean retryable → exit 1 para alertar al operador."""
    module = _load_script("run_due_reminders")
    result = RunDueRemindersResult(
        processed=True, leased_count=2, sent_count=0, retryable_count=2
    )
    monkeypatch.setattr(module, "build_reminder_dispatch_runner", lambda: _runner_returning(result))
    monkeypatch.setattr(sys, "argv", ["run_due_reminders.py"])
    assert module.main() == 1
