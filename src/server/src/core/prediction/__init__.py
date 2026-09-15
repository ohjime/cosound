"""Pure, framework-independent building blocks for CoSound prediction."""

from core.prediction.domain import (
    ListenerEvidence,
    Mix,
    MixLayer,
    SoundEvidence,
    VoteEvidence,
)
from core.prediction.selector import (
    CandidateScore,
    SelectionConfig,
    SelectionResult,
    enumerate_candidates,
    select_mix,
)

__all__ = [
    "CandidateScore",
    "ListenerEvidence",
    "Mix",
    "MixLayer",
    "SelectionConfig",
    "SelectionResult",
    "SoundEvidence",
    "VoteEvidence",
    "enumerate_candidates",
    "select_mix",
]
