"""Record-ingest receipts must survive on the workflow run (spec §4.3).

The receipt used to exist only in the browser tab that submitted the rows: a
refresh, a second analyst, or any other device saw a run with no counts. It
now rides the run's metadata and is re-typed at the projection boundary.
"""

from __future__ import annotations

import json

from agent.models import WorkflowRun, WorkflowStepState
from api._workflow_projection import project_workflow_run
from records.service_models import RecordIngestReceipt


def _run_with_metadata(metadata: dict[str, str]) -> WorkflowRun:
    return WorkflowRun(
        workflow_id="wf-1",
        knowledge_base_id="kb-1",
        trigger_event_type="records.ingested",
        steps=[WorkflowStepState(step_name="ingest")],
        metadata=dict(metadata),
    )


def test_receipt_json_metadata_projects_to_typed_receipt() -> None:
    receipt = RecordIngestReceipt(
        knowledge_base_id="kb-1",
        feed_name="pde",
        record_type="prescription_event",
        correlation_id="corr-1",
        accepted_count=10,
        rejected_count=2,
        suppressed_existing_count=3,
    )
    run = _run_with_metadata(
        {"record_receipt_json": json.dumps(receipt.model_dump(mode="json"))}
    )

    response = project_workflow_run(run)

    assert response.receipt is not None
    assert response.receipt.accepted_count == 10
    assert response.receipt.suppressed_existing_count == 3
    assert response.receipt.feed_name == "pde"


def test_missing_or_malformed_receipt_metadata_is_none() -> None:
    # A document run carries no receipt, and a run written by an older build
    # may carry something unparseable. Neither is an error: absence is.
    assert project_workflow_run(_run_with_metadata({})).receipt is None
    assert (
        project_workflow_run(
            _run_with_metadata({"record_receipt_json": "not json"})
        ).receipt
        is None
    )
