from __future__ import annotations


def test_policy_item_dtos_exist() -> None:
    from api.contracts import (
        PolicyItemDetailResponse,
        PolicyItemListResponse,
        PolicyItemSummaryResponse,
        PolicyTriageRequest,
    )

    req = PolicyTriageRequest(action="accept", note="ok")
    assert req.action == "accept"
    assert PolicyItemListResponse(items=[]).items == []
    assert "status" in PolicyItemSummaryResponse.model_fields
    assert "disposition" in PolicyItemDetailResponse.model_fields


def test_legacy_policy_gap_contracts_are_removed() -> None:
    import api.contracts as contracts

    for removed in (
        "PolicyGapSummaryResponse",
        "PolicyGapListResponse",
        "PolicyGapDetailResponse",
        "PolicyGapCaseListResponse",
        "PolicyBriefCreateRequest",
    ):
        assert not hasattr(contracts, removed), f"{removed} should be removed"
