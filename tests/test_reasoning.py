"""Tests for the reasoning engine: structured output, fallback, adaptive retry."""
import pytest

from backend.diagnostics import classify
from backend.analyzer import error_from_execution
from backend.models import AttemptRecord, ReasoningContext, SolveRequest
from backend.providers.base import AIProvider, ProviderError, ProviderResponse
from backend.reasoning.adaptive import AdaptiveController, MAX_ATTEMPTS
from backend.reasoning.engine import (
    ReasoningEngine,
    proposal_from_provider_response,
)
from backend.reasoning.strategies import gather_findings
from backend.runtimes import QiskitRuntime

BROKEN_CODE = "from qiskit import QuantumCircuit\n\nqc = QuantumCircuit(2)\nqc.cx(0, 2)\n"
GOOD_CODE = "from qiskit import QuantumCircuit\n\nqc = QuantumCircuit(2)\nqc.cx(0, 1)\n"

VALID_PROPOSAL = {
    "hypothesis": "Gate uses qubit index 2 in a 2-qubit circuit.",
    "diagnosis": "Qubit index out of range.",
    "proposed_fix": "Change index 2 to 1.",
    "patched_code": GOOD_CODE,
    "reasoning_summary": "Index 2 is invalid for size 2; index 1 is the last valid qubit.",
    "evidence": ["CircuitError: Index 2 out of range for size 2."],
    "confidence": 0.9,
    "next_action": "apply_fix",
}


def _runtime():
    return QiskitRuntime()


def _broken_context(attempts=None, level=1):
    rt = _runtime()
    execution = rt.execute(BROKEN_CODE)
    error = error_from_execution(execution, BROKEN_CODE)
    return ReasoningContext(
        code=BROKEN_CODE,
        framework="qiskit",
        error=error,
        diagnosis=classify(error),
        level=level,
        attempts=attempts or [],
    ), rt, error


class _ScriptedProvider(AIProvider):
    """Returns scripted responses based on whether failures appear in the prompt."""

    name = "scripted"

    def __init__(self, without_failures: dict, with_failures: dict | None = None):
        self.without_failures = without_failures
        self.with_failures = with_failures
        self.prompts: list[str] = []

    @property
    def model_id(self) -> str:
        return "scripted-model"

    def generate(self, prompt: str, *, timeout_s: float = 30.0) -> ProviderResponse:
        self.prompts.append(prompt)
        if "Previous failed attempts" in prompt and "none" not in prompt.split("## Previous failed attempts")[1][:20]:
            content = self.with_failures or self.without_failures
        else:
            content = self.without_failures
        return ProviderResponse(model=self.model_id, content=content, raw_text="")


# ------------------------------------------------ structured AI output
def test_valid_provider_response_validates():
    response = ProviderResponse(model="m", content=dict(VALID_PROPOSAL))
    proposal = proposal_from_provider_response(response)
    assert proposal.next_action == "apply_fix"
    assert proposal.patched_code == GOOD_CODE


@pytest.mark.parametrize(
    "mutation",
    [
        {"patched_code": ""},                       # empty fix
        {"next_action": "i_am_done"},               # invalid enum
        {"hypothesis": "", "diagnosis": ""},        # blanked required strings
        {"proposed_fix": None},                     # wrong type
    ],
)
def test_malformed_provider_responses_rejected(mutation):
    bad = dict(VALID_PROPOSAL)
    bad.update(mutation)
    response = ProviderResponse(model="m", content=bad)
    with pytest.raises(ProviderError):
        proposal_from_provider_response(response)


def test_non_object_content_rejected():
    with pytest.raises(ProviderError):
        proposal_from_provider_response(ProviderResponse(model="m", content=["not", "a", "dict"]))


# ------------------------------------------------ AI + heuristic priority
def test_ai_provider_used_when_configured():
    context, _, _ = _broken_context()
    provider = _ScriptedProvider(without_failures=dict(VALID_PROPOSAL))
    engine = ReasoningEngine(provider=provider)
    proposal, source = engine.propose(context)
    assert source == "ai"
    assert proposal.patched_code == GOOD_CODE
    assert provider.prompts  # the prompt contained evidence
    assert "CircuitError" in provider.prompts[0]


def test_heuristic_fallback_without_provider():
    context, _, _ = _broken_context()
    engine = ReasoningEngine(provider=None)
    proposal, source = engine.propose(context)
    assert source == "heuristic"
    assert proposal.patched_code != BROKEN_CODE
    assert "qc.cx(0, 1)" in proposal.patched_code


def test_malformed_ai_response_falls_back_to_heuristic():
    context, _, _ = _broken_context()
    provider = _ScriptedProvider(without_failures={"nonsense": True})
    engine = ReasoningEngine(provider=provider)
    proposal, source = engine.propose(context)
    assert source == "heuristic"
    assert "qc.cx(0, 1)" in proposal.patched_code


def test_failing_provider_falls_back_to_heuristic():
    class _Dead(AIProvider):
        name = "dead"
        @property
        def model_id(self): return "dead"
        def generate(self, prompt, *, timeout_s=30.0):
            raise ProviderError("down")

    context, _, _ = _broken_context()
    engine = ReasoningEngine(provider=_Dead())
    proposal, source = engine.propose(context)
    assert source == "heuristic"
    assert "qc.cx(0, 1)" in proposal.patched_code


# ------------------------------------------------ progressive levels
def test_higher_level_gathers_more_findings():
    context, _, _ = _broken_context()
    low = gather_findings(context.model_copy(update={"level": 1}))
    high = gather_findings(context.model_copy(update={"level": 5}))
    assert [f.level for f in low] == [1]
    assert [f.level for f in high] == [1, 2, 3, 4, 5]
    level3 = next(f for f in high if f.level == 3)
    assert any("2" in e and "qubit" in e.lower() for e in level3.evidence)
    level5 = next(f for f in high if f.level == 5)
    assert level5.data.get("distinct_errors") is not None


def test_ai_prompt_reflects_requested_level():
    context, _, _ = _broken_context(level=4)
    provider = _ScriptedProvider(without_failures=dict(VALID_PROPOSAL))
    ReasoningEngine(provider=provider).propose(context, framework_version="2.5.2")
    prompt = provider.prompts[0]
    assert "Environment analysis" in prompt       # level 4 ran
    assert "Hypothesis search" not in prompt      # level 5 did not
    assert "2.5.2" in prompt


# ------------------------------------------------ adaptive controller
def test_controller_solves_with_ai_fix():
    provider = _ScriptedProvider(without_failures=dict(VALID_PROPOSAL))
    controller = AdaptiveController(runtime=_runtime(), provider=provider)
    response = controller.solve(SolveRequest(code=BROKEN_CODE))
    assert response.status == "solved"
    assert response.fix.patched_code == GOOD_CODE
    assert response.verification.verified is True
    assert response.verification.execution.success is True  # real runtime evidence
    assert response.attempts[0].source == "ai"


def test_controller_heuristic_fallback_no_provider():
    controller = AdaptiveController(runtime=_runtime(), provider=None)
    response = controller.solve(SolveRequest(code=BROKEN_CODE))
    assert response.status == "solved"
    assert response.attempts[0].source == "heuristic"
    assert response.verification.verified is True


def test_new_hypothesis_after_failure():
    """Attempt 1 proposes a fix that still fails; attempt 2 uses the failure
    evidence to propose a different, correct fix."""
    still_broken = "from qiskit import QuantumCircuit\n\nqc = QuantumCircuit(2)\nqc.cx(0, 2)\nqc.cx(2, 0)\n"
    bad = dict(VALID_PROPOSAL, patched_code=still_broken, hypothesis="Hypothesis A: wrong order of gates.")
    good = dict(VALID_PROPOSAL, patched_code=GOOD_CODE, hypothesis="Hypothesis B: index 2 is simply invalid.")
    provider = _ScriptedProvider(without_failures=bad, with_failures=good)
    controller = AdaptiveController(runtime=_runtime(), provider=provider)
    response = controller.solve(SolveRequest(code=BROKEN_CODE))
    assert response.status == "solved"
    assert len(response.attempts) == 2
    assert response.attempts[0].verified is False
    assert response.attempts[0].why_failed
    assert response.attempts[1].verified is True
    assert response.attempts[1].hypothesis != response.attempts[0].hypothesis
    # The second prompt must contain the first attempt's failure evidence
    second_prompt = provider.prompts[1]
    assert "Attempt 1" in second_prompt
    assert response.attempts[0].why_failed.split("(")[0].strip() in second_prompt or "failed" in second_prompt


def test_level_progression_on_persistent_failure():
    """A provider that keeps proposing the same failing change must be
    escalated through the levels and stopped by the attempt bound."""
    always_failing = dict(VALID_PROPOSAL, patched_code=BROKEN_CODE)
    provider = _ScriptedProvider(without_failures=always_failing)
    controller = AdaptiveController(runtime=_runtime(), provider=provider)
    response = controller.solve(SolveRequest(code=BROKEN_CODE))
    assert response.status == "unsolved"
    assert len(response.attempts) == MAX_ATTEMPTS
    assert response.final_level == 5
    assert not response.fix
    assert response.verification.verified is False


def test_max_attempts_bounded_with_always_failing_ai():
    wrong_fix = dict(VALID_PROPOSAL, patched_code="from qiskit import QuantumCircuit\nqc = QuantumCircuit(2)\nqc.cx(9, 9)\n")
    provider = _ScriptedProvider(without_failures=wrong_fix)
    controller = AdaptiveController(runtime=_runtime(), provider=provider)
    response = controller.solve(SolveRequest(code=BROKEN_CODE))
    assert len(response.attempts) <= MAX_ATTEMPTS
    assert response.status == "unsolved"
    assert response.detail and "Maximum attempts" in response.detail


def test_give_up_respected_immediately():
    give_up = dict(VALID_PROPOSAL, next_action="give_up", patched_code="")
    provider = _ScriptedProvider(without_failures=give_up)
    controller = AdaptiveController(runtime=_runtime(), provider=provider)
    response = controller.solve(SolveRequest(code=BROKEN_CODE))
    assert response.status == "unsolved"
    assert len(response.attempts) == 0
    assert "No viable hypothesis" in response.detail


def test_duplicate_failed_patch_not_reexecuted():
    """After a failure, an identical patch must be rejected without running."""
    provider = _ScriptedProvider(without_failures=dict(VALID_PROPOSAL, patched_code=BROKEN_CODE))
    controller = AdaptiveController(runtime=_runtime(), provider=provider)
    response = controller.solve(SolveRequest(code=BROKEN_CODE))
    duplicate_records = [a for a in response.attempts if a.why_failed and "Repeated" in a.why_failed]
    assert duplicate_records, "expected repeated-patch rejection"
    assert duplicate_records[0].execution is None  # not executed again


def test_validator_is_source_of_truth_even_for_high_confidence_ai():
    """AI claims confidence 1.0; if the runtime disagrees, verified is False."""
    assert_confident = dict(VALID_PROPOSAL, patched_code="from qiskit import QuantumCircuit\nqc = QuantumCircuit(2)\nqc.x(7)\n", confidence=1.0)
    controller = AdaptiveController(runtime=_runtime(), provider=_ScriptedProvider(without_failures=assert_confident))
    response = controller.solve(SolveRequest(code=BROKEN_CODE))
    assert response.status == "unsolved"
    assert all(a.verified is False for a in response.attempts)
