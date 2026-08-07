"""Tests for the workflow step executor.

Built on the real in-memory run store, the real definition repository, the
real capability registry and the real audit service. The behaviours under
test — idempotency under redelivery, approval gating, failure modes — live in
the interaction between those, and a mocked registry would only assert that
this executor calls the methods it was written to call.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping

import pytest

from agent.adapters.in_memory import InMemoryWorkflowRunStore
from agent.models import (
    WorkflowRun,
    WorkflowRunStatus,
    WorkflowRunUpdate,
    WorkflowStepState,
    WorkflowStepStatus,
)
from auditlog.adapters.in_memory import InMemoryAuditLogRepository
from auditlog.service import AuditLogService
from capabilities.executors import clear_executors, register_executor
from capabilities.service import create_default_capability_registry_service
from events.adapters.in_memory import InMemoryEventBus
from events.types import AnyEvent, RecordsIngestedEvent, WorkflowStepQueuedEvent
from execution.deps import ExecutionDeps
from workflow_definitions.adapters.in_memory import InMemoryWorkflowDefinitionRepository
from workflow_definitions.executor import handle_workflow_step_queued
from workflow_definitions.models import (
    WorkflowDefinition,
    WorkflowFailureMode,
    WorkflowRetryPolicy,
    WorkflowStepDefinition,
)

_KB_ID = "kb-1"
_WORKFLOW_ID = "wf-run-1"
_DEFINITION_ID = "triage"
_VERSION = "v1"
_ACTOR = "operator-1"
_ROLES = ["analyst"]
# analytics.peer_context requires only `viewer` and is not an approval
# capability, so it is the least-constrained real capability to dispatch.
_CAPABILITY = "analytics.peer_context"


@pytest.fixture(autouse=True)
def clear_executor_registry() -> Iterator[None]:
    clear_executors()
    yield
    clear_executors()


class _CountingRegistry:
    """Wraps the real registry so dispatch attempts can be counted."""

    def __init__(self) -> None:
        self._inner = create_default_capability_registry_service()
        self.execute_call_count = 0

    def execute(self, capability_id: str, **kwargs: object):  # type: ignore[no-untyped-def]
        self.execute_call_count += 1
        return self._inner.execute(capability_id, **kwargs)  # type: ignore[arg-type]


def _steps(
    names: list[str],
    *,
    condition: str | None = None,
    requires_approval: bool = False,
    on_failure: WorkflowFailureMode = WorkflowFailureMode.FAIL_WORKFLOW,
    max_attempts: int = 1,
) -> list[WorkflowStepDefinition]:
    return [
        WorkflowStepDefinition(
            step_id=name,
            label=name.title(),
            capability_ref=_CAPABILITY,
            # Only the first step carries the varying attributes; later steps
            # exist to prove the chain advances.
            condition=condition if index == 0 else None,
            requires_human_approval=requires_approval if index == 0 else False,
            on_failure=on_failure,
            retry_policy=WorkflowRetryPolicy(max_attempts=max_attempts),
        )
        for index, name in enumerate(names)
    ]


def _definition(steps: list[WorkflowStepDefinition]) -> WorkflowDefinition:
    return WorkflowDefinition(
        definition_id=_DEFINITION_ID,
        knowledge_base_id=_KB_ID,
        domain_name="medicare_fraud",
        name="Triage",
        version=_VERSION,
        status="approved",
        allowed_capability_refs=[_CAPABILITY],
        steps=steps,
        created_by=_ACTOR,
        approved_by="supervisor-1",
    )


class _Harness:
    def __init__(
        self,
        *,
        steps: list[WorkflowStepDefinition],
        executor: Callable[[Mapping[str, object]], Mapping[str, object]] | None = None,
        actor_roles: list[str] | None = None,
        actor_user_id: str | None = _ACTOR,
    ) -> None:
        self.definitions = InMemoryWorkflowDefinitionRepository()
        self.definitions.save_definition(_definition(steps))
        self.store = InMemoryWorkflowRunStore()
        self.store.save_run(
            WorkflowRun(
                workflow_id=_WORKFLOW_ID,
                knowledge_base_id=_KB_ID,
                trigger_event_type="workflow_definition.requested",
                status=WorkflowRunStatus.QUEUED,
                steps=[WorkflowStepState(step_name=step.step_id) for step in steps],
                metadata={
                    "definition_id": _DEFINITION_ID,
                    "definition_version": _VERSION,
                },
                actor_user_id=actor_user_id,
                actor_roles=_ROLES if actor_roles is None else actor_roles,
            )
        )
        self.event_bus = InMemoryEventBus()
        self.registry = _CountingRegistry()
        self.audit = AuditLogService(InMemoryAuditLogRepository())
        if executor is not None:
            register_executor(_CAPABILITY, executor)
        else:
            register_executor(_CAPABILITY, _ok_executor)
        self.deps = ExecutionDeps(
            event_bus=self.event_bus,
            risk_service=None,
            score_run_repository=None,
            graph_repository=None,
            domain_config=None,
            workflow_definition_repository=self.definitions,
            workflow_run_store=self.store,
            capability_registry=self.registry,  # type: ignore[arg-type]
            audit_service=self.audit,
            workflow_domain_name="medicare_fraud",
            workflow_environment_tag="local",
        )

    def run(self) -> WorkflowRun:
        return self.store.get_run(_WORKFLOW_ID)

    def step(self, step_id: str) -> WorkflowStepState:
        return next(s for s in self.run().steps if s.step_name == step_id)

    def queued(self) -> list[WorkflowStepQueuedEvent]:
        return [
            event
            for event in self.event_bus.published_events
            if isinstance(event, WorkflowStepQueuedEvent)
        ]


def _ok_executor(payload: Mapping[str, object]) -> Mapping[str, object]:
    return {"risk_level": "high", "peer_count": 12}


def _boom_executor(payload: Mapping[str, object]) -> Mapping[str, object]:
    raise RuntimeError("capability exploded")


def _event(step_id: str) -> WorkflowStepQueuedEvent:
    return WorkflowStepQueuedEvent(
        correlation_id="corr-1",
        knowledge_base_id=_KB_ID,
        workflow_id=_WORKFLOW_ID,
        definition_id=_DEFINITION_ID,
        version=_VERSION,
        step_id=step_id,
    )


# --- happy path -------------------------------------------------------------


def test_runs_a_step_and_enqueues_the_next() -> None:
    harness = _Harness(steps=_steps(["enrich", "summarize"]))

    processed = handle_workflow_step_queued(_event("enrich"), harness.deps)

    assert processed == 1
    assert harness.step("enrich").status == WorkflowStepStatus.COMPLETED
    assert [event.step_id for event in harness.queued()] == ["summarize"]


def test_completes_the_run_after_the_final_step() -> None:
    harness = _Harness(steps=_steps(["enrich"]))

    handle_workflow_step_queued(_event("enrich"), harness.deps)

    assert harness.run().status == WorkflowRunStatus.COMPLETED
    assert harness.queued() == []


def test_records_the_step_output_for_later_conditions() -> None:
    """A later step's condition reads these, so they must be persisted."""
    harness = _Harness(steps=_steps(["enrich", "summarize"]))

    handle_workflow_step_queued(_event("enrich"), harness.deps)

    assert harness.step("enrich").metadata["risk_level"] == "high"


# --- conditions -------------------------------------------------------------


def test_a_false_condition_skips_the_step_without_executing_it() -> None:
    harness = _Harness(
        steps=_steps(["enrich", "summarize"], condition="summarize.k == 'v'")
    )
    # `summarize` has not run, so the condition is false.
    processed = handle_workflow_step_queued(_event("enrich"), harness.deps)

    assert processed == 1
    assert harness.step("enrich").status == WorkflowStepStatus.SKIPPED
    assert harness.registry.execute_call_count == 0


def test_a_skipped_step_still_advances_the_chain() -> None:
    """Otherwise one false condition stalls the whole run silently."""
    harness = _Harness(
        steps=_steps(["enrich", "summarize"], condition="summarize.k == 'v'")
    )

    handle_workflow_step_queued(_event("enrich"), harness.deps)

    assert [event.step_id for event in harness.queued()] == ["summarize"]


def test_a_true_condition_runs_the_step() -> None:
    harness = _Harness(steps=_steps(["enrich", "summarize"]))
    handle_workflow_step_queued(_event("enrich"), harness.deps)

    # `enrich` produced risk_level=high, so summarize's condition holds.
    stored = harness.definitions.get_definition(
        knowledge_base_id=_KB_ID,
        definition_id=_DEFINITION_ID,
        version=_VERSION,
    )
    assert stored is not None
    harness.definitions.update_definition(
        _definition(
            [
                stored.steps[0],
                WorkflowStepDefinition(
                    step_id="summarize",
                    label="Summarize",
                    capability_ref=_CAPABILITY,
                    condition="enrich.risk_level == 'high'",
                ),
            ]
        )
    )

    handle_workflow_step_queued(_event("summarize"), harness.deps)

    assert harness.step("summarize").status == WorkflowStepStatus.COMPLETED


# --- approval gate ----------------------------------------------------------


def test_an_approval_step_parks_the_run_and_does_not_dispatch() -> None:
    """The gate is server-side. A UI-only gate is not a gate."""
    harness = _Harness(steps=_steps(["notify"], requires_approval=True))

    processed = handle_workflow_step_queued(_event("notify"), harness.deps)

    assert processed == 0
    assert harness.run().status == WorkflowRunStatus.AWAITING_APPROVAL
    assert harness.registry.execute_call_count == 0


def test_a_parked_run_does_not_advance_on_redelivery() -> None:
    harness = _Harness(steps=_steps(["notify", "after"], requires_approval=True))
    handle_workflow_step_queued(_event("notify"), harness.deps)

    handle_workflow_step_queued(_event("notify"), harness.deps)

    assert harness.registry.execute_call_count == 0
    assert harness.queued() == []


# --- failure modes ----------------------------------------------------------


def test_fail_workflow_mode_terminates_the_run() -> None:
    harness = _Harness(
        steps=_steps(["enrich", "summarize"], on_failure=WorkflowFailureMode.FAIL_WORKFLOW),
        executor=_boom_executor,
    )

    handle_workflow_step_queued(_event("enrich"), harness.deps)

    assert harness.run().status == WorkflowRunStatus.FAILED
    assert harness.step("enrich").status == WorkflowStepStatus.FAILED
    assert harness.queued() == []


def test_continue_mode_proceeds_to_the_next_step() -> None:
    harness = _Harness(
        steps=_steps(["enrich", "summarize"], on_failure=WorkflowFailureMode.CONTINUE),
        executor=_boom_executor,
    )

    handle_workflow_step_queued(_event("enrich"), harness.deps)

    assert harness.step("enrich").status == WorkflowStepStatus.FAILED
    assert harness.run().status != WorkflowRunStatus.FAILED
    assert [event.step_id for event in harness.queued()] == ["summarize"]


def test_require_approval_mode_parks_the_run_on_failure() -> None:
    harness = _Harness(
        steps=_steps(
            ["enrich", "summarize"], on_failure=WorkflowFailureMode.REQUIRE_APPROVAL
        ),
        executor=_boom_executor,
    )

    handle_workflow_step_queued(_event("enrich"), harness.deps)

    assert harness.run().status == WorkflowRunStatus.AWAITING_APPROVAL
    assert harness.queued() == []


# --- retries ----------------------------------------------------------------


def test_a_step_retries_up_to_max_attempts_then_fails() -> None:
    harness = _Harness(
        steps=_steps(["enrich"], max_attempts=2), executor=_boom_executor
    )

    handle_workflow_step_queued(_event("enrich"), harness.deps)
    first_status = harness.step("enrich").status
    handle_workflow_step_queued(_event("enrich"), harness.deps)

    assert first_status == WorkflowStepStatus.PENDING  # retryable, not terminal
    assert harness.step("enrich").attempts == 2
    assert harness.step("enrich").status == WorkflowStepStatus.FAILED
    assert harness.run().status == WorkflowRunStatus.FAILED


def test_a_retryable_failure_requeues_the_same_step() -> None:
    harness = _Harness(
        steps=_steps(["enrich"], max_attempts=2), executor=_boom_executor
    )

    handle_workflow_step_queued(_event("enrich"), harness.deps)

    assert [event.step_id for event in harness.queued()] == ["enrich"]


# --- idempotency and cancellation -------------------------------------------


def test_stops_when_the_run_is_cancelled() -> None:
    harness = _Harness(steps=_steps(["enrich"]))
    harness.store.update_run(
        _WORKFLOW_ID, WorkflowRunUpdate(status=WorkflowRunStatus.CANCELLED)
    )

    processed = handle_workflow_step_queued(_event("enrich"), harness.deps)

    assert processed == 0
    assert harness.registry.execute_call_count == 0


def test_is_idempotent_under_duplicate_delivery() -> None:
    """Spec 6.4 — a redelivered step event must not execute the capability twice.

    Worse than a miscount: a side-effecting capability (case note draft,
    connector sync) would run twice for one authored step.
    """
    harness = _Harness(steps=_steps(["enrich", "summarize"]))
    event = _event("enrich")

    handle_workflow_step_queued(event, harness.deps)
    handle_workflow_step_queued(event, harness.deps)

    assert harness.registry.execute_call_count == 1
    assert [e.step_id for e in harness.queued()] == ["summarize"]


def test_a_skipped_step_is_not_re_evaluated_on_redelivery() -> None:
    harness = _Harness(
        steps=_steps(["enrich", "summarize"], condition="summarize.k == 'v'")
    )
    event = _event("enrich")
    handle_workflow_step_queued(event, harness.deps)

    processed = handle_workflow_step_queued(event, harness.deps)

    assert processed == 0
    assert [e.step_id for e in harness.queued()] == ["summarize"]


# --- guards -----------------------------------------------------------------


def test_ignores_an_unrelated_event_type() -> None:
    harness = _Harness(steps=_steps(["enrich"]))
    unrelated: AnyEvent = RecordsIngestedEvent(
        knowledge_base_id=_KB_ID, feed_name="f", record_type="r", record_count=1
    )

    assert handle_workflow_step_queued(unrelated, harness.deps) == 0


def test_returns_zero_when_a_dependency_is_absent() -> None:
    from dataclasses import replace

    harness = _Harness(steps=_steps(["enrich"]))

    assert (
        handle_workflow_step_queued(
            _event("enrich"), replace(harness.deps, workflow_run_store=None)
        )
        == 0
    )
    assert (
        handle_workflow_step_queued(
            _event("enrich"), replace(harness.deps, capability_registry=None)
        )
        == 0
    )


def test_a_run_with_no_recorded_actor_fails_rather_than_guessing() -> None:
    """Runs persisted before actor fields existed must not run as nobody.

    Inventing roles would bypass capability permissions for every
    workflow-dispatched call; dispatching with none would deny everything and
    look like a broken capability. Failing the run says what is actually wrong.
    """
    harness = _Harness(steps=_steps(["enrich"]), actor_user_id=None)

    processed = handle_workflow_step_queued(_event("enrich"), harness.deps)

    assert processed == 0
    assert harness.run().status == WorkflowRunStatus.FAILED
    assert harness.registry.execute_call_count == 0


def test_an_unknown_step_id_fails_the_run() -> None:
    harness = _Harness(steps=_steps(["enrich"]))

    processed = handle_workflow_step_queued(_event("nosuchstep"), harness.deps)

    assert processed == 0
    assert harness.run().status == WorkflowRunStatus.FAILED


def test_a_missing_definition_snapshot_fails_the_run() -> None:
    harness = _Harness(steps=_steps(["enrich"]))
    event = _event("enrich").model_copy(update={"version": "v-does-not-exist"})

    processed = handle_workflow_step_queued(event, harness.deps)

    assert processed == 0
    assert harness.run().status == WorkflowRunStatus.FAILED


def test_the_executor_is_registered_for_its_event_type() -> None:
    from execution.registry import registered_event_types

    assert "workflow.step.queued" in registered_event_types()


def test_dispatch_uses_the_runs_recorded_actor_not_an_invented_one() -> None:
    """Authorization must reflect who asked, or the permission model is theatre."""
    harness = _Harness(steps=_steps(["enrich"]), actor_roles=["viewer"])
    # analytics.peer_context permits viewer, so this still succeeds — the point
    # is that the roles travelled from the run rather than being fabricated.
    handle_workflow_step_queued(_event("enrich"), harness.deps)

    assert harness.step("enrich").status == WorkflowStepStatus.COMPLETED


def test_a_role_that_cannot_call_the_capability_fails_the_step() -> None:
    harness = _Harness(steps=_steps(["enrich"]), actor_roles=["nobody"])

    handle_workflow_step_queued(_event("enrich"), harness.deps)

    assert harness.step("enrich").status == WorkflowStepStatus.FAILED


def test_the_payload_carries_the_actor_for_capabilities_that_need_it() -> None:
    """`CapabilityExecutor` has no context argument, so the actor rides along.

    `connector.sync.status` re-authorizes internally and would see no roles
    otherwise, denying every workflow-dispatched call.
    """
    seen: list[Mapping[str, object]] = []

    def _capture(payload: Mapping[str, object]) -> Mapping[str, object]:
        seen.append(payload)
        return {}

    harness = _Harness(steps=_steps(["enrich"]), executor=_capture)

    handle_workflow_step_queued(_event("enrich"), harness.deps)

    assert seen[0]["actor_user_id"] == _ACTOR
    assert seen[0]["actor_roles"] == _ROLES
    assert seen[0]["knowledge_base_id"] == _KB_ID
