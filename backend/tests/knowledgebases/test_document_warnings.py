"""Repository contract tests for per-stage document warning persistence.

`set_stage_document_warnings` is the single write path for document warning
counts (agent.22): each pipeline stage (e.g. "parse", "extract") sets its own
contribution absolutely, and the document-level `warning_count` /
`warning_reasons` are maintained as the sum / sampled union across every
stage that has written. That gives two properties at once: replaying one
stage's handler converges instead of accumulating (BL-041 / Sprint 2026-35),
and a later stage's write can never overwrite an earlier stage's
contribution (the "obvious" naive fix -- switching the additive stage onto
the old absolute `set_document_warnings` -- traded the replay bug for a
data-loss bug; see the removed `record_document_warnings` /
`set_document_warnings` methods this suite used to cover).
"""

from __future__ import annotations

import pytest

from knowledgebases.adapters.in_memory import InMemoryKnowledgeBaseRepository
from knowledgebases.adapters.object_store import ObjectStoreKnowledgeBaseRepository
from knowledgebases.models import DocumentRecord
from knowledgebases.protocols import KnowledgeBaseRepository
from shared.types import KnowledgeBase
from shared.utils import utc_now
from storage.adapters.in_memory import InMemoryObjectStore


def _repositories() -> list[KnowledgeBaseRepository]:
    return [
        InMemoryKnowledgeBaseRepository(),
        ObjectStoreKnowledgeBaseRepository(InMemoryObjectStore()),
    ]


def _register(repository: KnowledgeBaseRepository) -> DocumentRecord:
    repository.create(
        KnowledgeBase(id="kb-1", name="KB", description="", created_at=utc_now())
    )
    return repository.add_document(
        DocumentRecord(
            id="doc-1",
            knowledge_base_id="kb-1",
            filename="claims.csv",
            content_type="text/csv",
        )
    )


def _record_stage(
    repository: KnowledgeBaseRepository,
    *,
    stage: str,
    count: int,
    reasons: list[str],
) -> DocumentRecord | None:
    return repository.set_stage_document_warnings(
        "kb-1", "doc-1", stage=stage, count=count, reasons=reasons
    )


@pytest.mark.parametrize("repository", _repositories(), ids=["in_memory", "object_store"])
def test_replaying_the_extract_stage_does_not_inflate_the_total(
    repository: KnowledgeBaseRepository,
) -> None:
    """2026-35 fixed the parse stage with an absolute setter. The extract
    stage (handle_entities_extracted, coordinator.py:2045) still did an
    additive record_document_warnings, so a retry still inflated.

    It was left deliberately: the two stages accumulate into one total by
    design, so switching it to the existing absolute setter would make
    extract overwrite parse -- trading a replay bug for a data-loss bug.
    Per-stage accounting is what closes both.
    """
    _register(repository)
    _record_stage(repository, stage="parse", count=2, reasons=["truncated table"])

    _record_stage(repository, stage="extract", count=3, reasons=["unknown type"])
    _record_stage(repository, stage="extract", count=3, reasons=["unknown type"])  # replay

    document = repository.get_document("kb-1", "doc-1")
    assert document is not None
    assert document.warning_count == 5  # 2 parse + 3 extract, not 8
    assert document.warning_reasons == ["truncated table", "unknown type"]


@pytest.mark.parametrize("repository", _repositories(), ids=["in_memory", "object_store"])
def test_a_later_stage_never_overwrites_an_earlier_stages_contribution(
    repository: KnowledgeBaseRepository,
) -> None:
    """The naive fix -- an absolute setter with no stage key -- would make
    extract's write clobber parse's. Keying the setter by stage rules that
    out structurally: writing "extract" only ever replaces the "extract"
    entry.
    """
    _register(repository)

    _record_stage(repository, stage="parse", count=2, reasons=["truncated table"])
    _record_stage(repository, stage="extract", count=3, reasons=["unknown type"])

    document = repository.get_document("kb-1", "doc-1")
    assert document is not None
    assert document.warning_count == 5
    assert document.warning_reasons == ["truncated table", "unknown type"]

    # Extract writes again (a second retry) -- parse's contribution must
    # still be intact, and extract's own value must still be absolute (not
    # additive on top of its own prior write).
    _record_stage(repository, stage="extract", count=4, reasons=["unknown type", "bad enum"])

    document = repository.get_document("kb-1", "doc-1")
    assert document is not None
    assert document.warning_count == 6  # 2 parse + 4 extract, not 2 + 3 + 4
    assert document.warning_reasons == ["truncated table", "unknown type", "bad enum"]


@pytest.mark.parametrize("repository", _repositories(), ids=["in_memory", "object_store"])
def test_set_stage_document_warnings_returns_the_updated_record(
    repository: KnowledgeBaseRepository,
) -> None:
    _register(repository)

    updated = _record_stage(repository, stage="parse", count=2, reasons=["truncated table"])

    assert updated is not None
    assert updated.warning_count == 2
    assert updated.warning_reasons == ["truncated table"]


@pytest.mark.parametrize("repository", _repositories(), ids=["in_memory", "object_store"])
def test_document_level_reasons_are_capped_at_ten_across_stages(
    repository: KnowledgeBaseRepository,
) -> None:
    _register(repository)

    _record_stage(
        repository,
        stage="parse",
        count=6,
        reasons=[f"parse-reason-{index}" for index in range(6)],
    )
    _record_stage(
        repository,
        stage="extract",
        count=6,
        reasons=[f"extract-reason-{index}" for index in range(6)],
    )

    document = repository.get_document("kb-1", "doc-1")
    assert document is not None
    assert document.warning_count == 12  # counts are exact, never capped
    assert len(document.warning_reasons) == 10  # reasons are a bounded sample
    assert document.warning_reasons[:6] == [f"parse-reason-{index}" for index in range(6)]


@pytest.mark.parametrize("repository", _repositories(), ids=["in_memory", "object_store"])
def test_set_stage_document_warnings_empty_reasons_clears_that_stages_reasons(
    repository: KnowledgeBaseRepository,
) -> None:
    """Absolute per stage: passing an empty list clears that stage's
    reasons rather than being ignored as "no update"."""
    _register(repository)

    _record_stage(repository, stage="parse", count=3, reasons=["stale reason"])
    _record_stage(repository, stage="parse", count=0, reasons=[])

    document = repository.get_document("kb-1", "doc-1")
    assert document is not None
    assert document.warning_count == 0
    assert document.warning_reasons == []


@pytest.mark.parametrize("repository", _repositories(), ids=["in_memory", "object_store"])
def test_set_stage_document_warnings_unknown_document_is_a_no_op(
    repository: KnowledgeBaseRepository,
) -> None:
    """Guard: knowledge base exists, but the document does not."""
    repository.create(
        KnowledgeBase(id="kb-1", name="KB", description="", created_at=utc_now())
    )

    result = repository.set_stage_document_warnings(
        "kb-1", "missing", stage="parse", count=1, reasons=[]
    )

    assert result is None
    assert repository.get_document("kb-1", "missing") is None


@pytest.mark.parametrize("repository", _repositories(), ids=["in_memory", "object_store"])
def test_set_stage_document_warnings_unknown_knowledge_base_is_a_no_op(
    repository: KnowledgeBaseRepository,
) -> None:
    """Guard: the knowledge base itself does not exist."""
    result = repository.set_stage_document_warnings(
        "missing-kb", "doc-1", stage="parse", count=1, reasons=[]
    )

    assert result is None
    assert repository.get_document("missing-kb", "doc-1") is None


@pytest.mark.parametrize("repository", _repositories(), ids=["in_memory", "object_store"])
def test_a_pre_existing_flat_total_is_discarded_not_folded_on_first_stage_write(
    repository: KnowledgeBaseRepository,
) -> None:
    """A document persisted before the per-stage ledger existed carries a
    non-zero warning_count/warning_reasons with no per-stage breakdown. That
    flat total was itself the *sum* of both stages under the old additive
    scheme (parse wrote absolutely, extract added on top) -- there is no way
    to recover which portion belonged to which stage from it. Folding the
    whole total into a synthetic entry would double-count every stage that
    goes on to rewrite, and -- since nothing ever clears it -- never
    converge. So the first stage write instead discards the old flat total
    and starts the per-stage ledger fresh with only that stage's own
    contribution: a transient undercount, never an overcount, converging to
    the correct sum once every stage has rewritten.
    """
    repository.create(
        KnowledgeBase(id="kb-1", name="KB", description="", created_at=utc_now())
    )
    repository.add_document(
        DocumentRecord(
            id="doc-1",
            knowledge_base_id="kb-1",
            filename="claims.csv",
            content_type="text/csv",
            warning_count=5,  # pre-2026-36: parse's 2 + extract's 3, accumulated
            warning_reasons=["pre-2026-36 truncated table", "pre-2026-36 unknown type"],
        )
    )

    # Parse reprocesses first: the flat "5" is discarded, not folded in.
    updated = _record_stage(repository, stage="parse", count=2, reasons=["truncated table"])
    assert updated is not None
    assert updated.warning_count == 2  # not 2 + 5 = 7 (the double-count trap), and not left at 5
    assert updated.warning_reasons == ["truncated table"]

    # Once extract also rewrites, the total converges to the correct sum of
    # the two real per-stage contributions -- not the old flat total plus
    # anything.
    updated = _record_stage(repository, stage="extract", count=3, reasons=["unknown type"])
    assert updated is not None
    assert updated.warning_count == 5  # 2 parse + 3 extract, not 2 + 5 + 3 = 10
    assert updated.warning_reasons == ["truncated table", "unknown type"]


@pytest.mark.parametrize("repository", _repositories(), ids=["in_memory", "object_store"])
def test_the_first_stage_write_starts_the_ledger_fresh_regardless_of_prior_total(
    repository: KnowledgeBaseRepository,
) -> None:
    """The discard-on-first-write behavior is unconditional: it applies
    whether the document's prior flat total was non-zero (a migrated
    document) or the pydantic default of 0 (a brand-new document) -- there
    is no special-casing on the prior value, which is exactly what rules
    out the double-count trap above."""
    _register(repository)  # warning_count=0 by default

    updated = _record_stage(repository, stage="parse", count=2, reasons=["truncated table"])

    assert updated is not None
    assert updated.warning_count == 2
    assert updated.warning_reasons == ["truncated table"]
    assert updated.stage_warning_counts == {"parse": 2}
