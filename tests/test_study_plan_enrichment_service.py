"""Tests del StudyPlanEnrichmentService."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from datetime import date

from schemas.planning import AcademicActivity
from services.planning.study_plan_enrichment_service import (
    StudyPlanEnrichmentService,
    _clean_text,
    _compact_text,
    _event_ids_by_subject,
    _int_or_none,
    _result_supports_primary_technique,
    build_study_plan_enrichment_service,
)


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_study_plan(rules: dict | None = None):
    plan = MagicMock()
    plan.rules = rules or {}
    plan.plan_events = []
    plan.model_copy.side_effect = lambda *, update: _MockPlan(update.get("rules", plan.rules))
    return plan


class _MockPlan:
    def __init__(self, rules):
        self.rules = rules
        self.plan_events = []

    def model_copy(self, *, update):
        return _MockPlan(update.get("rules", self.rules))


def _make_recommendation_service(*, ready: bool = True):
    svc = MagicMock()
    svc.status = MagicMock()
    svc.status.ready = ready
    return svc


# ── enrich_with_rag_guidance ─────────────────────────────────────────────────

def test_rag_guidance_returns_unchanged_when_no_primary_technique() -> None:
    svc = StudyPlanEnrichmentService(_make_recommendation_service())
    plan = _make_study_plan(rules={})

    result = svc.enrich_with_rag_guidance(plan, subjects=[], study_profile={})

    assert result is plan


def test_rag_guidance_returns_unchanged_when_service_not_ready() -> None:
    rec_svc = _make_recommendation_service(ready=False)
    svc = StudyPlanEnrichmentService(rec_svc)
    plan = _make_study_plan(rules={"primary_technique_id": "pomodoro"})

    result = svc.enrich_with_rag_guidance(plan, subjects=[], study_profile={})

    assert result is plan


def test_rag_guidance_returns_unchanged_on_exception() -> None:
    rec_svc = _make_recommendation_service()
    rec_svc.recommend_for_session.side_effect = RuntimeError("RAG down")
    svc = StudyPlanEnrichmentService(rec_svc)
    plan = _make_study_plan(rules={"primary_technique_id": "pomodoro"})

    result = svc.enrich_with_rag_guidance(plan, subjects=[], study_profile={})

    assert result is plan


def test_rag_guidance_returns_unchanged_when_no_source_chunks() -> None:
    rec_svc = _make_recommendation_service()
    rec_svc.recommend_for_session.return_value = MagicMock(
        source_chunks=[], answer="", cautions=[], relations_used=[], confidence=0.0
    )
    svc = StudyPlanEnrichmentService(rec_svc)
    plan = _make_study_plan(rules={"primary_technique_id": "pomodoro"})

    result = svc.enrich_with_rag_guidance(plan, subjects=[], study_profile={})

    assert result is plan


def test_rag_guidance_adds_rules_when_all_conditions_met() -> None:
    rec_svc = _make_recommendation_service()
    rec_svc.recommend_for_session.return_value = MagicMock(
        source_chunks=["technique.pomodoro::1"],
        answer="Usa intervalos de 25 minutos",
        cautions=["No uses el celular"],
        relations_used=["rel-1"],
        confidence=0.9,
    )
    svc = StudyPlanEnrichmentService(rec_svc)
    plan = _make_study_plan(rules={"primary_technique_id": "pomodoro"})

    result = svc.enrich_with_rag_guidance(plan, subjects=[], study_profile={})

    assert "rag_session_guidance" in result.rules
    assert result.rules["rag_session_guidance"]["primary_technique_id"] == "pomodoro"


# ── enrich_with_applied_methods ───────────────────────────────────────────────

def test_applied_methods_returns_unchanged_when_no_activities() -> None:
    svc = StudyPlanEnrichmentService(_make_recommendation_service())
    plan = _make_study_plan()

    result = svc.enrich_with_applied_methods(plan, subjects=[], academic_activities=[], study_profile={})

    assert result is plan


def _make_activity(**kwargs) -> AcademicActivity:
    defaults = dict(
        activity_id="act-1",
        activity_type="parcial",
        subject_name="Calculo",
        activity_title="Parcial 1",
        due_date=str(date.today()),
        status="pending",
    )
    defaults.update(kwargs)
    return AcademicActivity(**defaults)


def test_applied_methods_returns_unchanged_when_service_not_ready() -> None:
    rec_svc = _make_recommendation_service(ready=False)
    svc = StudyPlanEnrichmentService(rec_svc)
    plan = _make_study_plan()

    result = svc.enrich_with_applied_methods(
        plan, subjects=[], academic_activities=[_make_activity()], study_profile={}
    )

    assert result is plan


def test_applied_methods_returns_unchanged_when_service_raises() -> None:
    rec_svc = MagicMock()
    rec_svc.status = MagicMock(side_effect=RuntimeError("unavailable"))
    svc = StudyPlanEnrichmentService(rec_svc)
    plan = _make_study_plan()

    result = svc.enrich_with_applied_methods(
        plan, subjects=[], academic_activities=[_make_activity()], study_profile={}
    )

    assert result is plan


# ── mark_external_sync_as_pending ─────────────────────────────────────────────

def test_mark_external_sync_sets_defaults() -> None:
    svc = StudyPlanEnrichmentService(_make_recommendation_service())
    plan = _make_study_plan(rules={})

    result = svc.mark_external_sync_as_pending(plan)

    assert result.rules["external_sync_status"] == "not_requested"
    assert result.rules["external_sync_requires_confirmation"] is True
    assert "outlook_calendar" in result.rules["external_sync_targets"]


def test_mark_external_sync_does_not_overwrite_existing() -> None:
    svc = StudyPlanEnrichmentService(_make_recommendation_service())
    plan = _make_study_plan(rules={"external_sync_status": "synced"})

    result = svc.mark_external_sync_as_pending(plan)

    assert result.rules["external_sync_status"] == "synced"


# ── factory ───────────────────────────────────────────────────────────────────

def test_build_study_plan_enrichment_service_returns_instance() -> None:
    rec_svc = _make_recommendation_service()
    svc = build_study_plan_enrichment_service(rec_svc)
    assert isinstance(svc, StudyPlanEnrichmentService)


# ── private helpers ───────────────────────────────────────────────────────────

def test_clean_text_collapses_whitespace() -> None:
    assert _clean_text("  hello   world  ") == "hello world"


def test_compact_text_truncates_at_sentence_boundary() -> None:
    long_text = "Primera oración. " + "A" * 600
    result = _compact_text(long_text, max_chars=30)
    assert len(result) <= 35


def test_int_or_none_returns_int() -> None:
    assert _int_or_none("45") == 45


def test_int_or_none_returns_none_on_invalid() -> None:
    assert _int_or_none("abc") is None
    assert _int_or_none(None) is None


def test_result_supports_primary_technique_returns_true_on_match() -> None:
    chunks = ["technique.pomodoro::chunk-1", "technique.cornell::chunk-2"]
    assert _result_supports_primary_technique(chunks, "pomodoro") is True


def test_result_supports_primary_technique_returns_false_on_no_match() -> None:
    chunks = ["technique.cornell::chunk-1"]
    assert _result_supports_primary_technique(chunks, "pomodoro") is False


def test_event_ids_by_subject_groups_correctly() -> None:
    e1 = MagicMock()
    e1.titulo = "Estudio · Calculo"
    e1.id = "evt-1"
    e2 = MagicMock()
    e2.titulo = "Estudio · Calculo"
    e2.id = "evt-2"
    e3 = MagicMock()
    e3.titulo = "Estudio · Fisica"
    e3.id = "evt-3"

    result = _event_ids_by_subject([e1, e2, e3])

    assert result["calculo"] == ["evt-1", "evt-2"]
    assert result["fisica"] == ["evt-3"]
