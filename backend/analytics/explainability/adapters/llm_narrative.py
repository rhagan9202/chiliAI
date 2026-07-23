"""LLM-backed narrative generator, with deterministic degrade on any failure.

Renders selected explanation items into an evidence-grounded prompt and asks
the configured LLM to produce a markdown narrative. Per
`NarrativeGeneratorProtocol`, this adapter never raises: any llm-service
error, unexpected exception, or empty/malformed completion degrades to the
injected `NarrativeGeneratorProtocol` fallback (normally
`DeterministicNarrativeGenerator`) with a WARNING log, so a flaky or
misconfigured LLM provider never blocks evidence-pack generation.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Sequence

from analytics.explainability.models import (
    ExplanationContext,
    ExplanationItem,
    ExplanationNarrative,
    NarrativeSection,
)
from analytics.explainability.protocols import NarrativeGeneratorProtocol
from llm.exceptions import LlmError
from llm.protocols import LlmServiceProtocol
from llm.service_models import GenerateRequest, PromptTemplate

__all__ = ["LlmNarrativeGenerator"]

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are a fraud-analytics assistant writing an evidence-grounded narrative for "
    "a fraud investigator. Respond in markdown. Structure your response as a single "
    "opening summary paragraph of 1 to 3 sentences, followed by one or more sections "
    "each introduced by a '## ' heading. Ground every claim strictly in the listed "
    "evidence items below — do not fabricate identifiers, entities, quotes, or facts "
    "that are not present in the evidence."
)

_HEADING_SPLIT = re.compile(r"^## ", flags=re.MULTILINE)


class LlmNarrativeGenerator:
    """Summarize explanation items via an LLM, degrading to `fallback` on failure."""

    def __init__(
        self,
        llm_service: LlmServiceProtocol,
        *,
        fallback: NarrativeGeneratorProtocol,
        model_name: str,
        temperature: float,
        max_tokens: int,
    ) -> None:
        self._llm_service = llm_service
        self._fallback = fallback
        self._model_name = model_name
        self._temperature = temperature
        self._max_tokens = max_tokens

    def summarize(
        self, *, context: ExplanationContext, items: Sequence[ExplanationItem]
    ) -> ExplanationNarrative:
        try:
            # Request construction sits inside the guard so a validation
            # rejection (e.g. out-of-range sampling params) degrades instead
            # of breaking the never-raise contract.
            request = GenerateRequest(
                knowledge_base_id=context.knowledge_base_id,
                model_name=self._model_name,
                temperature=self._temperature,
                max_tokens=self._max_tokens,
                messages=[],
                prompt_template=PromptTemplate(
                    system_prompt=_SYSTEM_PROMPT,
                    user_prompt=_build_user_prompt(context, items),
                ),
            )
            response = self._llm_service.generate(request)
        except LlmError:
            logger.warning(
                "LlmNarrativeGenerator: llm service failed for kb=%s alert=%s; "
                "degrading to fallback narrative.",
                context.knowledge_base_id,
                context.alert.id,
                exc_info=True,
            )
            return self._fallback.summarize(context=context, items=items)
        except Exception:
            logger.warning(
                "LlmNarrativeGenerator: unexpected error for kb=%s alert=%s; "
                "degrading to fallback narrative.",
                context.knowledge_base_id,
                context.alert.id,
                exc_info=True,
            )
            return self._fallback.summarize(context=context, items=items)

        completion = response.completion.strip()
        if completion == "":
            logger.warning(
                "LlmNarrativeGenerator: empty completion for kb=%s alert=%s; "
                "degrading to fallback narrative.",
                context.knowledge_base_id,
                context.alert.id,
            )
            return self._fallback.summarize(context=context, items=items)

        narrative = _parse_narrative(completion, items)
        if not narrative.sections or narrative.summary == "":
            # A completion missing the mandated "## " headings, or opening
            # directly with a heading (no summary paragraph), is malformed
            # under the prompt contract; accepting it would persist packs
            # with empty narrative_sections or an empty reasoning lead.
            logger.warning(
                "LlmNarrativeGenerator: completion missing '## ' sections or "
                "opening summary for kb=%s alert=%s; degrading to fallback "
                "narrative.",
                context.knowledge_base_id,
                context.alert.id,
            )
            return self._fallback.summarize(context=context, items=items)
        return narrative


def _build_user_prompt(context: ExplanationContext, items: Sequence[ExplanationItem]) -> str:
    evidence_lines: list[str] = []
    for item in items:
        evidence_lines.append(
            f"- source_id: {item.source_id}\n"
            f"  quote: {item.quote}\n"
            f"  rationale: {item.rationale}\n"
            f"  score: {item.score:.2f}"
        )
    evidence_block = "\n".join(evidence_lines)
    scores_block = ", ".join(f"{name}={value:.2f}" for name, value in context.scores.items())

    return (
        f"Alert: {context.alert.title}\n"
        f"Scores: {scores_block}\n\n"
        "Evidence items:\n"
        f"{evidence_block}\n"
    )


def _parse_narrative(
    completion: str, items: Sequence[ExplanationItem]
) -> ExplanationNarrative:
    parts = _HEADING_SPLIT.split(completion)
    summary = parts[0].strip()
    blocks = parts[1:]
    # No-heading and heading-only shapes yield empty sections or an empty
    # summary here; the caller treats both as malformed and degrades.

    all_ids = [item.source_id for item in items]
    sections: list[NarrativeSection] = []
    for block in blocks:
        heading, _, body_raw = block.partition("\n")
        body = " ".join(body_raw.strip().splitlines())
        evidence_refs = [
            item.source_id
            for item in items
            if item.source_id in body or item.quote in body
        ]
        sections.append(
            NarrativeSection(
                heading=heading.strip(),
                body=body,
                evidence_refs=evidence_refs if evidence_refs else all_ids,
            )
        )

    return ExplanationNarrative(summary=summary, sections=sections)
