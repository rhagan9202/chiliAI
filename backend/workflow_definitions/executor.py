"""Executor for workflow definition runs.

Consumes one ``workflow.step.queued`` event per step: resolve the step against
the published definition snapshot, evaluate its condition, honour the approval
gate, dispatch its capability through the registry, apply the step's failure
mode, then chain the next step or finish the run.

Two properties are load-bearing:

**The step's own status is the idempotency claim.** A step already in a
terminal status returns 0 before dispatch. Redis Streams is at-least-once and
``reclaim_stale_pending`` can hand the same event to a second worker; without
this guard a side-effecting capability — a case note draft, a connector sync —
would run twice for one authored step.

**Authorization uses the run's recorded actor.** The run stores who requested
it, and every capability call is authorized as that actor. Inventing roles
here would bypass capability permissions for every workflow-dispatched call,
which is the entire point of having them.
"""

from __future__ import annotations

import logging

from agent.models import (
    TERMINAL_RUN_STATUSES,
    WorkflowRun,
    WorkflowRunStatus,
    WorkflowRunUpdate,
    WorkflowStepState,
    WorkflowStepStatus,
)
from agent.adapters.protocols import WorkflowRunStoreProtocol
from events.protocols import EventBus
from events.types import AnyEvent, WorkflowStepQueuedEvent
from execution.deps import ExecutionDeps
from execution.registry import register_handler
from shared.utils import utc_now
from workflow_definitions.conditions import ConditionSyntaxError, evaluate_condition
from workflow_definitions.models import (
    MetadataValue,
    WorkflowDefinition,
    WorkflowFailureMode,
    WorkflowStepDefinition,
)

__all__ = ["handle_workflow_step_queued"]

logger = logging.getLogger(__name__)

_TERMINAL_STEP_STATUSES = frozenset(
    {
        WorkflowStepStatus.COMPLETED,
        WorkflowStepStatus.FAILED,
        WorkflowStepStatus.SKIPPED,
    }
)


def handle_workflow_step_queued(event: AnyEvent, deps: ExecutionDeps) -> int:
    """Execute one workflow step, then chain the next or finish the run."""

    if not isinstance(event, WorkflowStepQueuedEvent):
        return 0
    run_store = deps.workflow_run_store
    definitions = deps.workflow_definition_repository
    registry = deps.capability_registry
    audit_service = deps.audit_service
    event_bus = deps.event_bus
    if (
        run_store is None
        or definitions is None
        or registry is None
        or audit_service is None
        or event_bus is None
    ):
        return 0

    try:
        run = run_store.get_run(event.workflow_id)
    except KeyError:
        logger.warning("Workflow step event for unknown run id=%s", event.workflow_id)
        return 0

    if run.status in TERMINAL_RUN_STATUSES:
        # Cancellation must actually stop the chain, not merely relabel it.
        return 0
    if run.status == WorkflowRunStatus.AWAITING_APPROVAL:
        # Parked on a person. A redelivery must not push past the gate.
        return 0

    state = _find_step_state(run, event.step_id)
    if state is None:
        return _fail_run(
            run_store, run, f"run has no step '{event.step_id}'"
        )
    if state.status in _TERMINAL_STEP_STATUSES:
        # The step's status is the claim: this event has already been served.
        return 0

    definition = definitions.get_definition(
        knowledge_base_id=event.knowledge_base_id,
        definition_id=event.definition_id,
        version=event.version,
    )
    if definition is None:
        return _fail_run(
            run_store,
            run,
            f"definition '{event.definition_id}' version '{event.version}' "
            "is no longer available",
        )
    step = _find_step_definition(definition, event.step_id)
    if step is None:
        return _fail_run(
            run_store,
            run,
            f"definition '{event.definition_id}' has no step '{event.step_id}'",
        )

    # Server-side gate. A UI-only approval gate is not a gate.
    if step.requires_human_approval and not _has_approval(run, step.step_id):
        _update_run_status(run_store, run, WorkflowRunStatus.AWAITING_APPROVAL)
        logger.info(
            "Workflow run parked for approval run=%s step=%s",
            run.workflow_id,
            step.step_id,
        )
        return 0

    if step.condition is not None:
        try:
            should_run = evaluate_condition(
                step.condition, outputs=_outputs_so_far(run)
            )
        except ConditionSyntaxError as exc:
            # Authoring-time validation rejects these, so reaching here means a
            # definition predating that validation. It cannot succeed on retry.
            return _fail_run(
                run_store, run, f"step '{step.step_id}' has an invalid condition: {exc}"
            )
        if not should_run:
            _record_step(
                run_store,
                run,
                step.step_id,
                status=WorkflowStepStatus.SKIPPED,
            )
            return _advance(run_store, event_bus, run, definition, step, deps)

    if run.actor_user_id is None:
        # A run persisted before actor fields existed. Dispatching with no
        # roles would deny every call and look like a broken capability;
        # inventing roles would bypass permissions entirely.
        return _fail_run(
            run_store,
            run,
            "run has no recorded actor, so its capability calls cannot be authorized",
        )

    envelope = registry.execute(
        step.capability_ref,
        payload=_payload_for(run, step),
        actor_user_id=run.actor_user_id,
        actor_roles=run.actor_roles,
        domain_name=deps.workflow_domain_name,
        environment_tag=deps.workflow_environment_tag,
        knowledge_base_id=run.knowledge_base_id,
        audit_service=audit_service,
    )

    attempts = state.attempts + 1
    if envelope.success:
        _record_step(
            run_store,
            run,
            step.step_id,
            status=WorkflowStepStatus.COMPLETED,
            attempts=attempts,
            output=envelope.output,
        )
        return _advance(run_store, event_bus, run, definition, step, deps)

    max_attempts = step.retry_policy.max_attempts if step.retry_policy else 1
    if attempts < max_attempts:
        # Left PENDING rather than FAILED: a terminal status would make the
        # requeued event skip itself as already-served.
        _record_step(
            run_store,
            run,
            step.step_id,
            status=WorkflowStepStatus.PENDING,
            attempts=attempts,
            error=envelope.error_message,
        )
        _publish_step(event_bus, run, definition, step.step_id)
        logger.info(
            "Workflow step failed, retrying run=%s step=%s attempt=%s/%s error=%s",
            run.workflow_id,
            step.step_id,
            attempts,
            max_attempts,
            envelope.error_code,
        )
        return 1

    _record_step(
        run_store,
        run,
        step.step_id,
        status=WorkflowStepStatus.FAILED,
        attempts=attempts,
        error=envelope.error_message,
    )
    logger.warning(
        "Workflow step exhausted attempts run=%s step=%s attempts=%s error=%s",
        run.workflow_id,
        step.step_id,
        attempts,
        envelope.error_code,
    )
    return _apply_failure_mode(run_store, event_bus, run, definition, step, deps)


# --- outcome handling -------------------------------------------------------


def _apply_failure_mode(
    run_store: WorkflowRunStoreProtocol,
    event_bus: EventBus,
    run: WorkflowRun,
    definition: WorkflowDefinition,
    step: WorkflowStepDefinition,
    deps: ExecutionDeps,
) -> int:
    if step.on_failure is WorkflowFailureMode.CONTINUE:
        return _advance(run_store, event_bus, run, definition, step, deps)
    if step.on_failure is WorkflowFailureMode.REQUIRE_APPROVAL:
        _update_run_status(run_store, run, WorkflowRunStatus.AWAITING_APPROVAL)
        return 1
    _update_run_status(run_store, run, WorkflowRunStatus.FAILED)
    return 1


def _advance(
    run_store: WorkflowRunStoreProtocol,
    event_bus: EventBus,
    run: WorkflowRun,
    definition: WorkflowDefinition,
    step: WorkflowStepDefinition,
    deps: ExecutionDeps,
) -> int:
    """Queue the next step, or complete the run when this was the last."""

    next_step = _next_step(definition, step.step_id)
    if next_step is None:
        _update_run_status(run_store, run, WorkflowRunStatus.COMPLETED)
        logger.info("Workflow run completed run=%s", run.workflow_id)
        return 1
    _update_run_status(run_store, run, WorkflowRunStatus.RUNNING)
    _publish_step(event_bus, run, definition, next_step.step_id)
    return 1


def _fail_run(
    run_store: WorkflowRunStoreProtocol, run: WorkflowRun, reason: str
) -> int:
    """Terminate a run that cannot succeed on any retry.

    Raising would burn the retry budget and dead-letter the event while
    leaving the run in flight with no recorded cause.
    """

    logger.error("Failing workflow run run=%s reason=%s", run.workflow_id, reason)
    _update_run_status(
        run_store, run, WorkflowRunStatus.FAILED, extra_metadata={"last_error": reason}
    )
    return 0


# --- persistence helpers ----------------------------------------------------


def _update_run_status(
    run_store: WorkflowRunStoreProtocol,
    run: WorkflowRun,
    status: WorkflowRunStatus,
    *,
    extra_metadata: dict[str, MetadataValue] | None = None,
) -> None:
    metadata = dict(run.metadata)
    if extra_metadata:
        metadata.update(extra_metadata)
    run_store.update_run(
        run.workflow_id,
        WorkflowRunUpdate(status=status, metadata=metadata, updated_at=utc_now()),
    )


def _record_step(
    run_store: WorkflowRunStoreProtocol,
    run: WorkflowRun,
    step_id: str,
    *,
    status: WorkflowStepStatus,
    attempts: int | None = None,
    output: dict[str, object] | None = None,
    error: str | None = None,
) -> None:
    """Persist one step's outcome, re-reading the run first.

    Re-reads rather than mutating the in-memory copy so a concurrent update to
    another step is not clobbered by writing back a stale `steps` list.
    """

    store = run_store
    current = store.get_run(run.workflow_id)
    steps: list[WorkflowStepState] = []
    for state in current.steps:
        if state.step_name != step_id:
            steps.append(state)
            continue
        metadata = dict(state.metadata)
        if output:
            metadata.update(_as_metadata(output))
        if error is not None:
            metadata["last_error"] = error
        steps.append(
            state.model_copy(
                update={
                    "status": status,
                    "attempts": state.attempts if attempts is None else attempts,
                    "metadata": metadata,
                }
            )
        )
    store.update_run(
        run.workflow_id, WorkflowRunUpdate(steps=steps, updated_at=utc_now())
    )


def _publish_step(
    event_bus: EventBus,
    run: WorkflowRun,
    definition: WorkflowDefinition,
    step_id: str,
) -> None:
    event_bus.publish(
        WorkflowStepQueuedEvent(
            correlation_id=run.workflow_id,
            knowledge_base_id=run.knowledge_base_id,
            workflow_id=run.workflow_id,
            definition_id=definition.definition_id,
            version=definition.version,
            step_id=step_id,
        )
    )


# --- lookups ----------------------------------------------------------------


def _find_step_state(run: WorkflowRun, step_id: str) -> WorkflowStepState | None:
    return next((s for s in run.steps if s.step_name == step_id), None)


def _find_step_definition(
    definition: WorkflowDefinition, step_id: str
) -> WorkflowStepDefinition | None:
    return next((s for s in definition.steps if s.step_id == step_id), None)


def _next_step(
    definition: WorkflowDefinition, step_id: str
) -> WorkflowStepDefinition | None:
    ids = [step.step_id for step in definition.steps]
    index = ids.index(step_id)
    if index + 1 >= len(definition.steps):
        return None
    return definition.steps[index + 1]


def _has_approval(run: WorkflowRun, step_id: str) -> bool:
    """Whether a human has approved this step.

    Approval is recorded on the run's metadata by the approval endpoint. Absent
    means not approved — the gate fails closed.
    """

    return bool(run.metadata.get(f"approved.{step_id}"))


def _outputs_so_far(run: WorkflowRun) -> dict[str, dict[str, object]]:
    """Completed steps' outputs, keyed by step id, for condition evaluation.

    Only COMPLETED steps contribute. A skipped or failed step produced nothing,
    and letting its (empty) metadata satisfy a condition would run a branch on
    data that does not exist.
    """

    return {
        state.step_name: dict(state.metadata)
        for state in run.steps
        if state.status is WorkflowStepStatus.COMPLETED
    }


def _payload_for(
    run: WorkflowRun, step: WorkflowStepDefinition
) -> dict[str, object]:
    # Business input only. The calling actor reaches an executor through
    # `ExecutionContext`, not through here — it used to ride in the payload
    # because the executor signature had nowhere else to put it.
    payload: dict[str, object] = {"knowledge_base_id": run.knowledge_base_id}
    for key, value in run.metadata.items():
        if key.startswith("input."):
            payload[key.removeprefix("input.")] = value
    for ref in step.input_refs:
        payload[ref] = run.metadata.get(f"input.{ref}")
    return payload


def _as_metadata(output: dict[str, object]) -> dict[str, MetadataValue]:
    """Narrow an envelope output to the metadata value types a run can store.

    Anything richer is dropped rather than stringified: a condition comparing
    against `"{'a': 1}"` would be comparing against an accident.
    """

    return {
        key: value
        for key, value in output.items()
        if isinstance(value, (str, int, float, bool))
    }


register_handler("workflow.step.queued", handle_workflow_step_queued)
