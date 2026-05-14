"""Smoke checks de arquitectura para la refactorizacion progresiva."""

from __future__ import annotations

import ast
import json
from pathlib import Path

from bootstrap.container import get_app_container


def test_langgraph_entrypoint_stays_stable() -> None:
    langgraph_config = json.loads(Path("langgraph.json").read_text(encoding="utf-8"))

    assert langgraph_config["graphs"]["support"] == "./src/agents/support/agent.py:agent"
    assert (
        langgraph_config["checkpointer"]["path"]
        == "./src/integrations/langgraph/checkpointer.py:create_checkpointer"
    )


def test_bootstrap_and_agent_import_smoke() -> None:
    from agents.support.agent import agent

    assert agent is not None
    assert get_app_container() is not None


def test_node_layer_repository_import_guardrail() -> None:
    root = Path("src/agents/support/nodes")
    violations: list[str] = []
    for file_path in root.rglob("*.py"):
        tree = ast.parse(file_path.read_text(encoding="utf-8"))
        repository_imports = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
            and isinstance(node.module, str)
            and _is_legacy_repository_module(node.module)
        }
        if repository_imports:
            violations.append(f"{file_path}: {sorted(repository_imports)!r}")

    assert violations == []


def test_state_module_exports_minimal_graph_state_api() -> None:
    from agents.support import state

    assert state.__all__ == ["AgentState", "Phase", "make_initial_state"]
    assert state.make_initial_state().__class__ is state.AgentState
    assert not hasattr(state, "Event")
    assert not hasattr(state, "SubjectItem")
    assert not hasattr(state, "StudyPlanState")
    assert not hasattr(state, "normalize_day")
    assert not hasattr(state, "validate_event")
    assert not hasattr(state, "CalendarState")


def test_state_module_no_longer_defines_moved_contracts_or_event_utilities() -> None:
    tree = ast.parse(
        Path("src/agents/support/state.py").read_text(encoding="utf-8")
    )
    class_names = {
        node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)
    }
    function_names = {
        node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
    }

    moved_classes = {
        "Event",
        "SubjectItem",
        "StudyPlanState",
        "PrioritiesState",
        "Constraints",
        "StudyProfile",
        "RemindersState",
        "CalendarState",
        "RawInputs",
    }
    moved_functions = {
        "normalize_day",
        "normalize_time",
        "validate_event",
        "sort_events",
        "new_event_id",
    }

    assert moved_classes.isdisjoint(class_names)
    assert moved_functions.isdisjoint(function_names)


def test_source_and_tests_import_only_minimal_state_api() -> None:
    allowed_names = {"AgentState", "Phase", "make_initial_state"}
    violations: list[str] = []
    for root in (Path("src"), Path("tests")):
        for file_path in root.rglob("*.py"):
            if file_path == Path("src/agents/support/state.py"):
                continue
            tree = ast.parse(file_path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.ImportFrom):
                    continue
                if node.module != "agents.support.state":
                    continue
                imported = {alias.name for alias in node.names}
                unexpected = imported - allowed_names
                if unexpected:
                    violations.append(f"{file_path}: {sorted(unexpected)!r}")

    assert violations == []


def test_productive_modules_do_not_import_legacy_repository_modules() -> None:
    violations: list[str] = []
    for file_path in Path("src").rglob("*.py"):
        tree = ast.parse(file_path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and isinstance(node.module, str):
                if _is_legacy_repository_module(node.module):
                    violations.append(f"{file_path}: {node.module}")
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if _is_legacy_repository_module(alias.name):
                        violations.append(f"{file_path}: {alias.name}")

    assert violations == []


def test_productive_modules_do_not_import_legacy_integration_modules() -> None:
    legacy_modules = {
        "auth.microsoft_auth",
        "agents.support.tools.llm",
        "agents.support.tools.microsoft_graph_clients",
        "agents.support.tools.langgraph_checkpointer",
    }
    violations: list[str] = []
    for file_path in Path("src").rglob("*.py"):
        tree = ast.parse(file_path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and isinstance(node.module, str):
                if node.module in legacy_modules:
                    violations.append(f"{file_path}: {node.module}")
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in legacy_modules:
                        violations.append(f"{file_path}: {alias.name}")

    assert violations == []


def test_service_layer_does_not_import_agent_modules() -> None:
    violations: list[str] = []
    for file_path in Path("src/services").rglob("*.py"):
        tree = ast.parse(file_path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and isinstance(node.module, str):
                if node.module.startswith("agents.support"):
                    violations.append(f"{file_path}: {node.module}")
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("agents.support"):
                        violations.append(f"{file_path}: {alias.name}")

    assert violations == []


def test_bootstrap_container_no_longer_imports_legacy_service_modules() -> None:
    tree = ast.parse(Path("src/bootstrap/container.py").read_text(encoding="utf-8"))
    violations: list[str] = []
    legacy_prefixes = (
        "agents.support.onboarding.service",
        "agents.support.personalization.service",
        "agents.support.planning.",
        "agents.support.reminders_service",
        "agents.support.scheduling.service",
        "agents.support.tools.calendar_outlook",
        "agents.support.tools.microsoft_todo",
    )
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and isinstance(node.module, str):
            if node.module.startswith(legacy_prefixes):
                violations.append(node.module)
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith(legacy_prefixes):
                    violations.append(alias.name)

    assert violations == []


def test_productive_modules_do_not_import_legacy_conversational_flow_modules() -> None:
    legacy_modules = {
        "agents.support.scheduling.schedule_capture_service",
        "agents.support.scheduling.schedule_parsing_service",
        "agents.support.scheduling.schedule_pending_resolution_service",
        "agents.support.scheduling.schedule_review_service",
        "agents.support.scheduling.schedule_draft_service",
        "agents.support.priorities.priority_capture_service",
        "agents.support.planning.persistence_support",
    }
    violations: list[str] = []
    for file_path in Path("src").rglob("*.py"):
        tree = ast.parse(file_path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and isinstance(node.module, str):
                if node.module in legacy_modules:
                    violations.append(f"{file_path}: {node.module}")
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in legacy_modules:
                        violations.append(f"{file_path}: {alias.name}")

    assert violations == []


def test_hotspot_nodes_are_now_thin_wrappers() -> None:
    hotspot_nodes = (
        Path("src/agents/support/nodes/collect_profile/node.py"),
        Path("src/agents/support/nodes/collect_extracurricular_details/node.py"),
    )
    for file_path in hotspot_nodes:
        tree = ast.parse(file_path.read_text(encoding="utf-8"))
        definitions = [
            node
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        ]
        assert definitions == [], str(file_path)


def test_removed_legacy_wrapper_paths_are_absent() -> None:
    removed_paths = (
        Path("src/auth/microsoft_auth.py"),
        Path("src/agents/support/onboarding/config.py"),
        Path("src/agents/support/onboarding/email_sender.py"),
        Path("src/agents/support/onboarding/repository.py"),
        Path("src/agents/support/onboarding/service.py"),
        Path("src/agents/support/personalization/config.py"),
        Path("src/agents/support/personalization/models.py"),
        Path("src/agents/support/personalization/parser.py"),
        Path("src/agents/support/personalization/questionnaire.py"),
        Path("src/agents/support/personalization/repository.py"),
        Path("src/agents/support/personalization/runtime.py"),
        Path("src/agents/support/personalization/scoring.py"),
        Path("src/agents/support/personalization/service.py"),
        Path("src/agents/support/planning/instances_repository.py"),
        Path("src/agents/support/planning/materialization_service.py"),
        Path("src/agents/support/planning/persistence_service.py"),
        Path("src/agents/support/planning/repository.py"),
        Path("src/agents/support/planning/state_helpers.py"),
        Path("src/agents/support/planning/study_plan_sync_service.py"),
        Path("src/agents/support/planning/study_planning_service.py"),
        Path("src/agents/support/planning/tracking_repository.py"),
        Path("src/agents/support/planning/tracking_service.py"),
        Path("src/agents/support/planning/tracking_state_helpers.py"),
        Path("src/agents/support/priorities/state_helpers.py"),
        Path("src/agents/support/priorities/subject_prioritization_service.py"),
        Path("src/agents/support/reminders_dispatcher.py"),
        Path("src/agents/support/reminders_repository.py"),
        Path("src/agents/support/reminders_service.py"),
        Path("src/agents/support/reminders_state_helpers.py"),
        Path("src/agents/support/scheduling/constants.py"),
        Path("src/agents/support/scheduling/models.py"),
        Path("src/agents/support/scheduling/repository.py"),
        Path("src/agents/support/scheduling/service.py"),
        Path("src/agents/support/tools/llm.py"),
        Path("src/agents/support/tools/microsoft_graph_clients.py"),
        Path("src/agents/support/tools/langgraph_checkpointer.py"),
        Path("src/agents/support/tools/activity_matching.py"),
        Path("src/agents/support/tools/calendar_outlook.py"),
        Path("src/agents/support/tools/calendar_google.py"),
        Path("src/agents/support/tools/calendar_logic.py"),
        Path("src/agents/support/tools/db_config.py"),
        Path("src/agents/support/tools/event_labels.py"),
        Path("src/agents/support/tools/microsoft_graph_state_repository.py"),
        Path("src/agents/support/tools/microsoft_graph_sync_repository.py"),
        Path("src/agents/support/tools/microsoft_todo.py"),
        Path("src/agents/support/tools/schedule_parser.py"),
        Path("src/agents/support/tools/schedule_renderer.py"),
        Path("src/agents/support/scheduling/schedule_capture_service.py"),
        Path("src/agents/support/scheduling/schedule_parsing_service.py"),
        Path("src/agents/support/scheduling/schedule_pending_resolution_service.py"),
        Path("src/agents/support/scheduling/schedule_review_service.py"),
        Path("src/agents/support/scheduling/schedule_draft_service.py"),
        Path("src/agents/support/priorities/priority_capture_service.py"),
        Path("src/agents/support/planning/persistence_support.py"),
    )
    for file_path in removed_paths:
        assert not file_path.exists(), str(file_path)


def test_agents_productive_modules_do_not_import_repositories_or_integrations_directly() -> None:
    violations: list[str] = []
    for file_path in Path("src/agents").rglob("*.py"):
        for module in _collect_import_modules(file_path):
            if module.startswith(("repositories.", "integrations.")):
                violations.append(f"{file_path}: {module}")

    assert violations == []


def test_schemas_layer_does_not_import_upper_layers() -> None:
    violations: list[str] = []
    for file_path in Path("src/schemas").rglob("*.py"):
        for module in _collect_import_modules(file_path):
            if module.startswith(("agents.", "services.", "repositories.", "integrations.")):
                violations.append(f"{file_path}: {module}")

    assert violations == []


def test_tools_directory_is_frozen_curated_zone() -> None:
    allowed_paths = {
        Path("src/agents/support/tools/__init__.py"),
        Path("src/agents/support/tools/db.py"),
    }
    current_paths = set(Path("src/agents/support/tools").glob("*.py"))

    assert current_paths == allowed_paths


def test_state_module_only_depends_on_scheduling_models_within_services() -> None:
    state_path = Path("src/agents/support/state.py")
    violations: list[str] = []
    allowed_service_modules = {"services.scheduling.models"}
    for module in _collect_import_modules(state_path):
        if module.startswith(("repositories.", "integrations.")):
            violations.append(module)
        if module.startswith("services.") and module not in allowed_service_modules:
            violations.append(module)

    assert violations == []


def test_future_capability_placeholders_exist() -> None:
    expected_paths = (
        Path("src/rag/README.md"),
        Path("src/rag/ingestion/__init__.py"),
        Path("src/rag/retrieval/__init__.py"),
        Path("src/rag/prompting/__init__.py"),
        Path("src/integrations/whatsapp/__init__.py"),
        Path("src/integrations/whatsapp/README.md"),
    )

    for file_path in expected_paths:
        assert file_path.exists(), str(file_path)


def test_source_and_tests_do_not_import_legacy_wrapper_modules() -> None:
    compatibility_entrypoints = {
        Path("src/agents/support/dependencies.py"),
        Path("tests/test_refactor_guardrails.py"),
    }
    violations: list[str] = []
    for root in (Path("src"), Path("tests")):
        for file_path in root.rglob("*.py"):
            if file_path in compatibility_entrypoints:
                continue
            for module in _collect_import_modules(file_path):
                if _is_legacy_wrapper_module(module):
                    violations.append(f"{file_path}: {module}")

    assert violations == []


def test_agent_layer_accesses_container_only_through_dependencies_module() -> None:
    allowed_paths = {
        Path("src/agents/support/dependencies.py"),
    }
    violations: list[str] = []
    for file_path in Path("src/agents").rglob("*.py"):
        if file_path in allowed_paths:
            continue
        for module in _collect_import_modules(file_path):
            if module == "bootstrap.container":
                violations.append(f"{file_path}: {module}")

    assert violations == []


def _is_legacy_repository_module(module: str) -> bool:
    if module.startswith("agents.support.") and module.endswith(".repository"):
        return True
    return module in {
        "agents.support.planning.instances_repository",
        "agents.support.planning.tracking_repository",
        "agents.support.reminders_repository",
        "agents.support.tools.microsoft_graph_state_repository",
        "agents.support.tools.microsoft_graph_sync_repository",
    }


def _collect_import_modules(file_path: Path) -> list[str]:
    tree = ast.parse(file_path.read_text(encoding="utf-8"))
    module_name = _module_name_for_path(file_path)
    package_name = (
        module_name
        if file_path.name == "__init__.py"
        else module_name.rsplit(".", maxsplit=1)[0]
    )
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and isinstance(node.module, str):
            if node.level:
                modules.append(
                    _resolve_relative_import(
                        package_name,
                        module=node.module,
                        level=node.level,
                    )
                )
            else:
                modules.append(node.module)
        if isinstance(node, ast.ImportFrom) and node.module is None and node.level:
            modules.append(
                _resolve_relative_import(
                    package_name,
                    module="",
                    level=node.level,
                )
            )
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
    return modules


def _is_legacy_wrapper_module(module: str) -> bool:
    return module in {
        "agents.support.onboarding",
        "agents.support.onboarding.config",
        "agents.support.onboarding.email_sender",
        "agents.support.onboarding.repository",
        "agents.support.onboarding.service",
        "agents.support.personalization",
        "agents.support.personalization.config",
        "agents.support.personalization.models",
        "agents.support.personalization.parser",
        "agents.support.personalization.questionnaire",
        "agents.support.personalization.repository",
        "agents.support.personalization.runtime",
        "agents.support.personalization.scoring",
        "agents.support.personalization.service",
        "agents.support.planning",
        "agents.support.planning.instances_repository",
        "agents.support.planning.materialization_service",
        "agents.support.planning.persistence_service",
        "agents.support.planning.repository",
        "agents.support.planning.state_helpers",
        "agents.support.planning.study_plan_sync_service",
        "agents.support.planning.study_planning_service",
        "agents.support.planning.tracking_repository",
        "agents.support.planning.tracking_service",
        "agents.support.planning.tracking_state_helpers",
        "agents.support.priorities",
        "agents.support.priorities.state_helpers",
        "agents.support.priorities.subject_prioritization_service",
        "agents.support.reminders_dispatcher",
        "agents.support.reminders_repository",
        "agents.support.reminders_service",
        "agents.support.reminders_state_helpers",
        "agents.support.scheduling.constants",
        "agents.support.scheduling.models",
        "agents.support.scheduling.repository",
        "agents.support.scheduling.service",
        "agents.support.tools.activity_matching",
        "agents.support.tools.calendar_google",
        "agents.support.tools.calendar_logic",
        "agents.support.tools.db",
        "agents.support.tools.db_config",
        "agents.support.tools.event_labels",
        "agents.support.tools.microsoft_graph_state_repository",
        "agents.support.tools.microsoft_graph_sync_repository",
        "agents.support.tools.schedule_renderer",
    }


def _module_name_for_path(file_path: Path) -> str:
    relative = file_path.with_suffix("")
    if relative.parts and relative.parts[0] in {"src", "tests"}:
        relative = Path(*relative.parts[1:])
    parts = list(relative.parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _resolve_relative_import(package_name: str, *, module: str, level: int) -> str:
    package_parts = package_name.split(".")
    keep_parts = len(package_parts) - max(level - 1, 0)
    base = package_parts[:keep_parts]
    if module:
        base.extend(module.split("."))
    return ".".join(base)
