"""Reasoning engine: turns evidence into a validated fix proposal.

Priority: AI provider (when configured) -> heuristic knowledge base.
Model text is never trusted: responses must validate against
ReasoningProposal; malformed output falls back to heuristics.

Only concise summaries and evidence are kept — no private chain-of-thought
is stored or returned.
"""
from __future__ import annotations

import json

from backend.fix_engine import propose_fixes
from backend.models import ReasoningContext, ReasoningProposal
from backend.providers.base import AIProvider, ProviderError, ProviderResponse

_ALLOWED_NEXT_ACTIONS = {"apply_fix", "need_more_info", "give_up"}

_PROMPT_SCHEMA = """{
  "hypothesis": "one-sentence statement of the suspected root cause",
  "diagnosis": "one-sentence diagnosis summary",
  "proposed_fix": "short description of the change",
  "patched_code": "the COMPLETE corrected source file, ready to execute",
  "reasoning_summary": "2-3 sentences: evidence and why this change addresses the cause",
  "evidence": ["short factual evidence strings"],
  "confidence": 0.0,
  "next_action": "apply_fix | need_more_info | give_up"
}"""


def build_prompt(context: ReasoningContext, findings) -> str:
    """Build the reasoning prompt from context + strategy findings."""
    finding_blocks = []
    for f in findings:
        finding_blocks.append(
            f"### {f.title} (level {f.level})\n{f.summary}\n"
            + "\n".join(f"- {e}" for e in f.evidence)
        )
    attempt_blocks = []
    for a in context.attempts:
        attempt_blocks.append(
            f"Attempt {a.attempt} (level {a.level}, {a.source}): {a.hypothesis}\n"
            f"  change: {a.fix_description}\n"
            f"  result: {a.why_failed}"
        )
    knowledge = ", ".join(context.knowledge) or "none"
    env = ""
    if context.environment:
        env = f"Environment: {context.environment.model_dump_json()}"

    return f"""You are a quantum computing runtime-error solver for the {context.framework or 'unknown'} framework.

Analyze the evidence and propose ONE fix. Respond with ONLY a JSON object of this exact schema:
{_PROMPT_SCHEMA}

Rules:
- "patched_code" must be the complete corrected file that can be executed as-is.
- "next_action" must be "apply_fix" unless the evidence is genuinely insufficient.
- Never claim a fix is verified; the runtime will test your proposal.
- Do not repeat changes listed as failed attempts.
- Use only the evidence below. Be concise.

## Findings
{chr(10).join(finding_blocks) if finding_blocks else 'none'}

## Previous failed attempts
{chr(10).join(attempt_blocks) if attempt_blocks else 'none'}

## Knowledge patterns available
{knowledge}

## Source code
```python
{context.code}
```

## Runtime error
{context.error.model_dump_json() if context.error else 'none'}

## Diagnosis
{context.diagnosis.model_dump_json() if context.diagnosis else 'none'}

{env}
"""


def proposal_from_provider_response(response: ProviderResponse) -> ReasoningProposal:
    """Validate a provider payload against the schema; reject malformed output."""
    content = response.content
    if not isinstance(content, dict):
        raise ProviderError("Provider content is not a JSON object")
    try:
        proposal = ReasoningProposal.model_validate(content)
    except Exception as exc:  # pydantic ValidationError or wrong shape
        raise ProviderError(f"Malformed reasoning response: {exc}") from exc
    if proposal.next_action not in _ALLOWED_NEXT_ACTIONS:
        raise ProviderError(f"Invalid next_action: {proposal.next_action!r}")
    if proposal.next_action == "apply_fix" and not proposal.patched_code.strip():
        raise ProviderError("apply_fix proposal without patched_code")
    return proposal


def proposal_from_heuristic(context: ReasoningContext) -> ReasoningProposal | None:
    """Wrap an existing knowledge-base/heuristic fix as a proposal."""
    if context.diagnosis is None or context.error is None:
        return None
    candidates = propose_fixes(context.code, context.diagnosis)
    if not candidates:
        return None
    strategy, description, patched_code, conf = candidates[0]
    alt = [c[0] for c in candidates[1:]]
    return ReasoningProposal(
        hypothesis=(context.diagnosis.hypotheses[0].cause if context.diagnosis.hypotheses else context.diagnosis.summary),
        diagnosis=context.diagnosis.summary,
        proposed_fix=description,
        patched_code=patched_code,
        reasoning_summary=(
            f"Heuristic knowledge-base strategy {strategy!r} matched diagnosis "
            f"{context.diagnosis.category!r}."
        ),
        evidence=[f"strategy={strategy}", f"alternatives={alt}" if alt else "no alternatives"],
        confidence=conf,
        next_action="apply_fix",
    )


class ReasoningEngine:
    def __init__(self, provider: AIProvider | None = None, provider_timeout_s: float = 30.0):
        self.provider = provider
        self.provider_timeout_s = provider_timeout_s

    def propose(
        self, context: ReasoningContext, framework_version: str | None = None
    ) -> tuple[ReasoningProposal, str]:
        """Return (proposal, source) where source is "ai" or "heuristic".

        Raises no exceptions: any provider failure degrades to the heuristic.
        """
        findings = None
        if self.provider is not None:
            try:
                findings = self._findings(context, framework_version)
                prompt = build_prompt(context, findings)
                response = self.provider.timed_generate(prompt, timeout_s=self.provider_timeout_s)
                return proposal_from_provider_response(response), "ai"
            except Exception:
                # Any provider failure (ProviderError, unexpected bug, bad
                # output) degrades to heuristics; never bypasses the validator.
                pass
        heuristic = proposal_from_heuristic(context)
        if heuristic is not None:
            return heuristic, "heuristic"
        return ReasoningProposal(
            hypothesis="No viable hypothesis from available evidence.",
            diagnosis=context.diagnosis.summary if context.diagnosis else "unknown",
            proposed_fix="none",
            patched_code="",
            reasoning_summary="Heuristic engine and provider produced no applicable fix.",
            evidence=[],
            confidence=0.0,
            next_action="give_up",
        ), "heuristic"

    def _findings(self, context: ReasoningContext, framework_version: str | None):
        from backend.reasoning.strategies import gather_findings

        return gather_findings(context, framework_version)
