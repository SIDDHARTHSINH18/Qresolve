"""Knowledge base of known quantum error patterns.

Each pattern maps parsed error characteristics to causes/suggestions and,
where deterministic, a fix strategy. This is a hand-written seed KB; the AI
reasoning engine will extend it later.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class KnownPattern:
    pattern_id: str
    exception_types: list[str]
    message_regexes: list[str] = field(default_factory=list)
    summary: str = ""
    causes: list[tuple[str, str, float]] = field(default_factory=list)  # (cause, suggestion, confidence)
    fix_strategy: str | None = None


PATTERNS: list[KnownPattern] = [
    KnownPattern(
        pattern_id="qubit_index_out_of_range",
        exception_types=["IndexError", "CircuitError", "QiskitError"],
        message_regexes=[r"index", r"qubit", r"out of range", r"out-of-range"],
        summary="A gate referenced a qubit index that does not exist in the circuit.",
        causes=[
            (
                "The circuit was created with fewer qubits than the highest index used by a gate.",
                "Either reduce the gate's qubit indices to valid ones (0..n-1), or create the "
                "QuantumCircuit with more qubits.",
                0.8,
            ),
        ],
        fix_strategy="qubit_index",
    ),
    KnownPattern(
        pattern_id="clbit_index_out_of_range",
        exception_types=["IndexError", "CircuitError", "QiskitError"],
        message_regexes=[r"clbit", r"classical"],
        summary="A measurement/condition referenced a classical bit index that does not exist.",
        causes=[
            (
                "The circuit was created with fewer classical bits than referenced.",
                "Add more classical bits to the circuit or use a valid clbit index.",
                0.7,
            ),
        ],
    ),
    KnownPattern(
        pattern_id="cirq_duplicate_qids",
        exception_types=["ValueError"],
        message_regexes=[r"duplicate qids"],
        summary="A Cirq gate was applied to the same qubit more than once.",
        causes=[
            (
                "A multi-qubit gate received repeated qubits (e.g. cirq.CNOT(q, q)); "
                "every qubit operand of a gate must be distinct.",
                "Pass distinct qubits to the gate (e.g. allocate a second LineQubit).",
                0.8,
            ),
        ],
    ),
    KnownPattern(
        pattern_id="cirq_wrong_qubit_count",
        exception_types=["ValueError"],
        message_regexes=[r"wrong number of qubits"],
        summary="A Cirq gate received the wrong number of qubit operands.",
        causes=[
            (
                "The gate's arity does not match the qubits supplied (e.g. a two-qubit "
                "gate called with a single qubit).",
                "Supply exactly the number of qubits the gate expects.",
                0.8,
            ),
        ],
    ),
    KnownPattern(
        pattern_id="cirq_no_measurements",
        exception_types=["ValueError"],
        message_regexes=[r"no measurements to sample"],
        summary="simulator.run() was called on a circuit with no measurement gates.",
        causes=[
            (
                "run() samples measurement results, but the circuit contains no "
                "cirq.measure(...).",
                "Add cirq.measure(qubit, key='...') before running, or use "
                "simulator.simulate() to inspect the final state without sampling.",
                0.85,
            ),
        ],
    ),
    KnownPattern(
        pattern_id="cirq_overlapping_operations",
        exception_types=["ValueError"],
        message_regexes=[r"overlapping operations"],
        summary="Two operations were placed on the same qubit within one Cirq moment.",
        causes=[
            (
                "A moment contains operations acting on a shared qubit, which cannot "
                "happen simultaneously.",
                "Move the conflicting operations into separate moments (or append them "
                "to the circuit sequentially instead of one Moment).",
                0.75,
            ),
        ],
    ),
    KnownPattern(
        pattern_id="cirq_unknown_attribute",
        exception_types=["AttributeError"],
        message_regexes=[r"has no attribute"],
        summary="A referenced cirq attribute/gate does not exist in the installed version.",
        causes=[
            (
                "The code accessed cirq.<Name> that is not defined — misspelled, "
                "removed, or renamed across cirq versions.",
                "Use a valid cirq symbol for the installed version (e.g. cirq.X, "
                "cirq.CNOT, cirq.H).",
                0.7,
            ),
        ],
    ),
    KnownPattern(
        pattern_id="pl_wire_not_on_device",
        exception_types=["WireError"],
        message_regexes=[r"wires not found on the device"],
        summary="A PennyLane operation referenced a wire that does not exist on the device.",
        causes=[
            (
                "The device was built with fewer wires than the operation's wire index "
                "(e.g. qml.device('lightning.qubit', wires=2) with a gate on wires=[0, 5]).",
                "Use wire indices within 0..wires-1, or create the device with more wires.",
                0.8,
            ),
        ],
    ),
    KnownPattern(
        pattern_id="pl_duplicate_wires",
        exception_types=["ValueError"],
        message_regexes=[r"control wires must be different"],
        summary="A PennyLane controlled gate was given the same wire as control and target.",
        causes=[
            (
                "A gate such as qml.CNOT(wires=[0, 0]) repeats a wire; control and target "
                "must be distinct wires.",
                "Pass two distinct wire indices to the controlled gate.",
                0.8,
            ),
        ],
    ),
    KnownPattern(
        pattern_id="pl_wrong_number_of_wires",
        exception_types=["ValueError"],
        message_regexes=[r"wrong number of wires"],
        summary="A PennyLane operation received the wrong number of wires.",
        causes=[
            (
                "The gate's wire arity does not match the wires supplied (e.g. a two-wire "
                "gate called with wires=[0], or a one-wire gate called with wires=[]).",
                "Pass exactly the number of wires the operation expects.",
                0.8,
            ),
        ],
    ),
    KnownPattern(
        pattern_id="pl_device_not_found",
        exception_types=["DeviceError"],
        message_regexes=[r"does not exist"],
        summary="qml.device() was called with a device name that does not exist.",
        causes=[
            (
                "The device name is misspelled or belongs to a plugin that is not installed; "
                "built-in names include 'default.qubit' and 'lightning.qubit'.",
                "Use a built-in device name such as qml.device('default.qubit', wires=n), or "
                "install the plugin that provides the device.",
                0.8,
            ),
        ],
    ),
    KnownPattern(
        pattern_id="pl_qnode_bad_return",
        exception_types=["QuantumFunctionError"],
        message_regexes=[r"must return either a single measurement"],
        summary="A PennyLane QNode quantum function did not return measurement object(s).",
        causes=[
            (
                "The function decorated with @qml.qnode must return a measurement "
                "(e.g. qml.expval(qml.PauliZ(0))) or a sequence of measurements, not raw "
                "values or nothing at all.",
                "Return one or more measurements (qml.expval/probs/sample/state) from the "
                "quantum function.",
                0.85,
            ),
        ],
    ),
    KnownPattern(
        pattern_id="qasm2_parse_error",
        exception_types=["QASM2ParseError"],
        message_regexes=[],
        summary="The program is not valid OpenQASM 2.0 and could not be parsed.",
        causes=[
            (
                "The OpenQASM source contains a syntax error, an undeclared gate/register, "
                "or a qubit/classical-bit index that is out of range for its declared "
                "register size.",
                "Check the reported line/column: registers must be declared with qreg/creg "
                "before use, indices must be within the declared size, and every gate must "
                "be one of the standard qelib1.inc gates.",
                0.75,
            ),
        ],
    ),
    KnownPattern(
        pattern_id="qasm_version_unsupported",
        exception_types=["NotImplementedError"],
        message_regexes=[r"openqasm 3 is not supported"],
        summary="The program is OpenQASM 3, which this QResolve build does not execute.",
        causes=[
            (
                "Only OpenQASM 2.0 (qelib1.inc) is parsed and simulated in this build; "
                "OpenQASM 3 language constructs are not claimed to be compatible.",
                "Rewrite the program in OpenQASM 2.0 (qreg/creg, include \"qelib1.inc\") "
                "to run it here.",
                0.9,
            ),
        ],
    ),
    KnownPattern(
        pattern_id="name_not_defined",
        exception_types=["NameError"],
        summary="A name used in the code is not defined.",
        causes=[
            (
                "A variable or function is used before being defined, or is misspelled / not imported.",
                "Define the name before use, fix the spelling, or add the missing import.",
                0.7,
            ),
        ],
    ),
    KnownPattern(
        pattern_id="missing_import",
        exception_types=["ImportError", "ModuleNotFoundError"],
        summary="A required module or symbol could not be imported.",
        causes=[
            (
                "The module is not installed in the runtime environment, or the symbol does not "
                "exist in the installed framework version.",
                "Install the package or adjust the import for the installed framework version.",
                0.8,
            ),
        ],
    ),
    KnownPattern(
        pattern_id="type_error",
        exception_types=["TypeError"],
        summary="A call received arguments of the wrong type or count.",
        causes=[
            (
                "A gate/method was called with the wrong number or type of arguments.",
                "Check the framework API signature for the failing call.",
                0.6,
            ),
        ],
    ),
]


def match_pattern(exception_type: str | None, message: str | None) -> KnownPattern | None:
    """Return the first pattern matching the parsed error (None if unknown)."""
    if not exception_type and not message:
        return None
    msg = (message or "").lower()
    for p in PATTERNS:
        if exception_type in p.exception_types:
            if not p.message_regexes or any(re_needle in msg for re_needle in
                                            [r.lower() for r in p.message_regexes]):
                return p
    # Fall back to exception-type-only match
    for p in PATTERNS:
        if exception_type in p.exception_types:
            return p
    return None
