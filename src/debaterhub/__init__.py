"""debaterhub SDK — Python client for human-vs-AI IPDA debates."""

from ._version import __version__
from .logging_setup import configure_from_env as _configure_logging

# Honor DEBATERHUB_LOG_LEVEL / DEBATERHUB_VERBOSE on import so apps that
# set them in their env get verbose SDK output without extra wiring.
_configure_logging()
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
from .formats import (
    FORMAT_REGISTRY,
    FormatSpec,
    IPDA_SPEC,
    LD_SPEC,
    PF_SPEC,
    SpeechSpec,
    get_format_spec,
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
from .flow_schema import (
    CXExchange,
    CXPeriod,
    FlowData,
    FlowGenerateRequest,
    FlowPage,
    FlowPageSpeech,
    PageEvidenceCard,
    PageFlowArgument,
    SpeechTranscript,
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
from .topics import (
    TopicPrepClient,
    TopicPrepError,
    TopicPrepEvent,
    TopicPrepStart,
)
from .counters import (
    CounterPrepClient,
    CounterPrepError,
    CounterEvent,
    CounterPrepStart,
    CounterType,
)
from .search import (
    SearchHit,
    TopicSearchClient,
    TopicSearchError,
)

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
    # Formats
    "FORMAT_REGISTRY",
    "FormatSpec",
    "IPDA_SPEC",
    "LD_SPEC",
    "PF_SPEC",
    "SpeechSpec",
    "get_format_spec",
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
    # Flow schema (page-grouped, wire contract with frontend)
    "FlowData",
    "FlowPage",
    "FlowPageSpeech",
    "PageFlowArgument",
    "PageEvidenceCard",
    "CXPeriod",
    "CXExchange",
    "FlowGenerateRequest",
    "SpeechTranscript",
    # Topic prep (v1)
    "TopicPrepClient",
    "TopicPrepEvent",
    "TopicPrepStart",
    "TopicPrepError",
    # Counter-argument prep (v1)
    "CounterPrepClient",
    "CounterEvent",
    "CounterPrepStart",
    "CounterPrepError",
    "CounterType",
    # Topic search — semantic search over a prepped topic's belief tree
    "TopicSearchClient",
    "SearchHit",
    "TopicSearchError",
    # Exceptions
    "DebatehubError",
    "ConfigValidationError",
    "ConnectionError",
    "DispatchError",
    "WarmupError",
    "SessionNotConnectedError",
    "ProtocolError",
]
