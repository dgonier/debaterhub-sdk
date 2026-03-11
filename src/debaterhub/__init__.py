"""debaterhub SDK — Python client for human-vs-AI IPDA debates."""

from ._version import __version__
from .client import DebateClient
from .config import ConnectionDetails, DebateClientConfig, DebateConfig
from .constants import (
    AFF_ACTIVE,
    AFF_SPEECHES,
    IPDA_SPEECH_ORDER,
    IS_CX_SPEECH,
    NEG_ACTIVE,
    NEG_SPEECHES,
    SPEECH_SIDE,
    SPEECH_TIME_LIMITS,
)
from .events import (
    BeliefTreeEvent,
    CoachingHintEvent,
    CXAnswerEvent,
    CXQuestionEvent,
    DebateEvent,
    DebateEventHandler,
    DebateInitializingEvent,
    DebateReadyEvent,
    ErrorEvent,
    EvidenceResultEvent,
    FlowUpdateEvent,
    JudgeResultEvent,
    JudgingStartedEvent,
    SpeechProgressEvent,
    SpeechScoredEvent,
    SpeechTextEvent,
    TurnSignalEvent,
)
from .models import (
    Argument,
    ArgumentStatus,
    Belief,
    BeliefTree,
    ClashPoint,
    CoachingCategory,
    CoachingHint,
    CoachingPriority,
    EvidenceCard,
    FlowArgument,
    FlowState,
    JudgeDecision,
    PerSpeechFeedback,
    ScoringDimension,
    SpeechScore,
    VotingIssue,
)
from .exceptions import (
    ConfigValidationError,
    ConnectionError,
    DebatehubError,
    DispatchError,
    ProtocolError,
    SessionNotConnectedError,
    WarmupError,
)
from .session import ManagedDebateSession
from .state import DebateTurnTracker

__all__ = [
    "__version__",
    # Client
    "DebateClient",
    "ManagedDebateSession",
    # Config
    "DebateClientConfig",
    "DebateConfig",
    "ConnectionDetails",
    # Events
    "DebateEvent",
    "DebateEventHandler",
    "DebateInitializingEvent",
    "DebateReadyEvent",
    "TurnSignalEvent",
    "SpeechTextEvent",
    "SpeechProgressEvent",
    "FlowUpdateEvent",
    "CoachingHintEvent",
    "SpeechScoredEvent",
    "CXQuestionEvent",
    "CXAnswerEvent",
    "EvidenceResultEvent",
    "JudgingStartedEvent",
    "JudgeResultEvent",
    "ErrorEvent",
    "BeliefTreeEvent",
    # State
    "DebateTurnTracker",
    # Constants
    "IPDA_SPEECH_ORDER",
    "SPEECH_TIME_LIMITS",
    "AFF_ACTIVE",
    "NEG_ACTIVE",
    "AFF_SPEECHES",
    "NEG_SPEECHES",
    "IS_CX_SPEECH",
    "SPEECH_SIDE",
    # Models
    "BeliefTree",
    "Belief",
    "Argument",
    "ArgumentStatus",
    "EvidenceCard",
    "FlowState",
    "FlowArgument",
    "VotingIssue",
    "ClashPoint",
    "ScoringDimension",
    "SpeechScore",
    "JudgeDecision",
    "PerSpeechFeedback",
    "CoachingHint",
    "CoachingPriority",
    "CoachingCategory",
    # Exceptions
    "DebatehubError",
    "ConfigValidationError",
    "ConnectionError",
    "DispatchError",
    "WarmupError",
    "SessionNotConnectedError",
    "ProtocolError",
]
