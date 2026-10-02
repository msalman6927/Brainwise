from enum import StrEnum

from backend.core.errors import InvalidPhaseError


class Phase(StrEnum):
    IDLE = "idle"
    TOPIC_SET = "topic_set"
    ASSESSING = "assessing"
    SCORING = "scoring"
    EXPLAINING = "explaining"
    FOLLOW_UP = "follow_up"


# AGENTS.md §2 — the LLM never decides a transition; services call assert_transition().
TRANSITIONS: dict[Phase, frozenset[Phase]] = {
    Phase.IDLE: frozenset({Phase.TOPIC_SET}),
    Phase.TOPIC_SET: frozenset({Phase.ASSESSING}),
    Phase.ASSESSING: frozenset({Phase.ASSESSING, Phase.SCORING}),
    Phase.SCORING: frozenset({Phase.EXPLAINING}),
    # EXPLAINING -> EXPLAINING: a dropped stream leaves the thread here; the next
    # message regenerates the explanation instead of stranding the student (§9 resumable).
    Phase.EXPLAINING: frozenset({Phase.FOLLOW_UP, Phase.EXPLAINING}),
    Phase.FOLLOW_UP: frozenset({Phase.FOLLOW_UP, Phase.IDLE}),
}


def can_transition(current: Phase, target: Phase) -> bool:
    return target in TRANSITIONS[current]


def assert_transition(current: Phase, target: Phase) -> None:
    if not can_transition(current, target):
        raise InvalidPhaseError(f"illegal transition {current} -> {target}")
