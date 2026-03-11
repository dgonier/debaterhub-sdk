"""Shared fixtures for E2E tests.

Provides a simulated agent that speaks the IPDA protocol over an in-memory
data channel, so tests can exercise the full SDK without a real LiveKit server.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Dict, List, Optional
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

from debaterhub.config import DebateConfig
from debaterhub.constants import (
    AFF_ACTIVE,
    IPDA_SPEECH_ORDER,
    IS_CX_SPEECH,
    SPEECH_SIDE,
    SPEECH_TIME_LIMITS,
)
from debaterhub.events import DebateEventHandler
from debaterhub.session import ManagedDebateSession


# ---------------------------------------------------------------------------
# Simulated data channel (replaces LiveKit)
# ---------------------------------------------------------------------------

class SimulatedDataChannel:
    """In-memory bidirectional data channel between SDK session and agent."""

    def __init__(self) -> None:
        self._session_callback: Optional[Callable] = None
        self._agent_callback: Optional[Callable] = None
        self.session_sent: List[Dict[str, Any]] = []
        self.agent_sent: List[Dict[str, Any]] = []

    def set_session_callback(self, cb: Callable) -> None:
        self._session_callback = cb

    def set_agent_callback(self, cb: Callable) -> None:
        self._agent_callback = cb

    async def send_to_session(self, data: Dict[str, Any]) -> None:
        """Agent → Session (server events)."""
        self.agent_sent.append(data)
        if self._session_callback:
            raw = json.dumps(data).encode()
            await self._session_callback(raw, "debate")

    async def send_to_agent(self, data: Dict[str, Any]) -> None:
        """Session → Agent (client commands)."""
        self.session_sent.append(data)
        if self._agent_callback:
            # Schedule as a task so it doesn't block the caller
            asyncio.create_task(self._agent_callback(data))


class MockParticipant:
    """Drop-in replacement for DataOnlyParticipant using SimulatedDataChannel."""

    def __init__(self, channel: SimulatedDataChannel) -> None:
        self._channel = channel
        self._connected = False
        self._on_data: Optional[Callable] = None

    @property
    def connected(self) -> bool:
        return self._connected

    async def connect(self) -> None:
        self._connected = True
        self._channel.set_session_callback(self._on_data)

    async def disconnect(self) -> None:
        self._connected = False

    async def send(self, data: Dict[str, Any]) -> None:
        await self._channel.send_to_agent(data)


# ---------------------------------------------------------------------------
# Simulated IPDA Agent
# ---------------------------------------------------------------------------

MOCK_SPEECHES = {
    "AC": (
        "The affirmative constructive argues that universal basic income is a net "
        "positive for society. First, UBI eliminates poverty by providing a floor "
        "below which no citizen can fall. Studies from Finland and Kenya show direct "
        "cash transfers reduce poverty rates by 40 percent. Second, UBI stimulates "
        "economic growth by increasing consumer spending. The Roosevelt Institute "
        "estimates a 12.5 percent GDP growth over 8 years. Third, UBI promotes "
        "entrepreneurship by reducing risk. When basic needs are met, individuals "
        "are more likely to start businesses. Therefore the resolution is affirmed."
    ),
    "NC": (
        "The negative constructive rejects the resolution. First, UBI is fiscally "
        "unsustainable. Providing 12,000 dollars per year to 250 million adults "
        "costs 3 trillion annually, exceeding the entire federal discretionary "
        "budget. Second, UBI creates moral hazard. The Congressional Budget Office "
        "estimates a 2 to 4 percent reduction in labor supply. Third, UBI fails to "
        "address structural inequalities. Cash alone cannot fix systemic barriers "
        "in education, healthcare, and housing. Targeted programs deliver better "
        "outcomes per dollar spent. The resolution is negated."
    ),
    "1AR": (
        "Extending the affirmative case. On the fiscal argument, the negative "
        "ignores that UBI replaces existing welfare programs worth 700 billion, "
        "and a modest VAT of 10 percent generates 800 billion more. The net cost "
        "is manageable. On labor supply, the Finland trial showed no significant "
        "reduction in employment while increasing well-being. On structural "
        "inequality, UBI is complementary, not exclusive. We maintain targeted "
        "programs alongside UBI. The affirmative case stands."
    ),
    "NR": (
        "The negative rebuttal. The affirmative's funding math does not add up. "
        "Replacing welfare still leaves a 1.5 trillion gap. A 10 percent VAT is "
        "regressive and hurts the very people UBI aims to help. The Finland trial "
        "was limited to 2000 participants and cannot scale. On complementary "
        "programs, if we keep targeted programs then UBI is just additional "
        "spending with diminishing returns. The negative position holds."
    ),
    "2AR": (
        "In final rebuttal, the affirmative notes that the negative concedes UBI "
        "eliminates poverty. Their objections are about degree, not direction. "
        "Progressive VAT designs exist. The negative offers no alternative that "
        "achieves universal coverage. Affirm the resolution."
    ),
}

CX_EXCHANGES = {
    "AC-CX": [
        ("How would you fund UBI without increasing the deficit?", "Through a combination of VAT and welfare consolidation."),
        ("Doesn't a VAT disproportionately affect low-income earners?", "Not with exemptions on essentials like food and medicine."),
        ("What about inflation from increased consumer spending?", "The Fed can manage monetary policy to contain inflation."),
    ],
    "NC-CX": [
        ("You claim UBI is unsustainable. What about Alaska's PFD?", "Alaska's dividend is funded by oil revenue, not taxes."),
        ("Aren't targeted programs already failing millions in poverty?", "They need reform, not replacement with a blunt instrument."),
        ("How do you address automation displacing workers?", "Job retraining and education investment are more effective."),
    ],
}


@dataclass
class SimulatedAgent:
    """Simulates the debate agent following the IPDA protocol.

    Sends events in the correct order, respects timing metadata, and
    responds to human speech submissions.
    """

    channel: SimulatedDataChannel
    config: DebateConfig
    ai_side: str = ""
    _speech_index: int = 0
    _events_log: List[Dict[str, Any]] = field(default_factory=list)
    _waiting_for_human: bool = False
    _started: bool = False

    def __post_init__(self) -> None:
        self.ai_side = "neg" if self.config.human_side == "aff" else "aff"
        self.channel.set_agent_callback(self._on_client_message)

    def _is_ai_speech(self, speech_type: str) -> bool:
        side = SPEECH_SIDE.get(speech_type, "")
        return side == self.ai_side

    async def start_debate(self) -> None:
        """Kick off the simulated debate."""
        self._started = True

        # debate_initializing
        await self._emit({
            "type": "debate_initializing",
            "topic": self.config.topic,
            "humanSide": self.config.human_side,
            "message": "Preparing debate...",
            "estimatedSeconds": 5,
        })
        await asyncio.sleep(0.05)

        # belief_tree
        await self._emit({
            "type": "belief_tree",
            "tree": {
                "topic": self.config.topic,
                "generatedAt": "2026-03-07T08:00:00Z",
                "prepTimeSeconds": 5.0,
                "beliefs": [
                    {
                        "id": "b1",
                        "label": "Poverty Elimination",
                        "claim": "UBI eliminates extreme poverty",
                        "side": "aff",
                        "arguments": [
                            {
                                "id": "a1",
                                "claim": "Direct cash transfers reduce poverty by 40%",
                                "warrant": "Finland and Kenya trials demonstrate measurable poverty reduction",
                                "impact": "Millions lifted out of extreme poverty",
                                "label": "Cash Transfers",
                                "evidence": [
                                    {
                                        "tag": "Kela 2020",
                                        "fullText": "The Finnish basic income experiment showed improved well-being and modest employment effects.",
                                        "source": "Kela Research",
                                        "cite": "Kela 2020",
                                        "fullCite": "Kela Research Department, 'Results of Finland Basic Income Experiment', 2020",
                                        "selectedTexts": ["improved well-being", "modest employment effects"],
                                        "sourceUrl": "https://example.com/kela-2020",
                                    },
                                    {
                                        "tag": "GiveDirectly 2019",
                                        "fullText": "GiveDirectly Kenya trials showed 42% reduction in days without food.",
                                        "source": "GiveDirectly",
                                        "cite": "GiveDirectly 2019",
                                        "fullCite": "GiveDirectly, 'Long-Term Effects of Cash Transfers in Kenya', 2019",
                                        "selectedTexts": ["42% reduction in days without food"],
                                        "sourceUrl": "https://example.com/givedirectly",
                                    },
                                ],
                            },
                        ],
                    },
                    {
                        "id": "b2",
                        "label": "Economic Growth",
                        "claim": "UBI stimulates economic growth through consumer spending",
                        "side": "aff",
                        "arguments": [
                            {
                                "id": "a2",
                                "claim": "Consumer spending increases GDP by 12.5% over 8 years",
                                "warrant": "Roosevelt Institute macroeconomic modeling",
                                "impact": "Sustained long-term economic growth",
                                "label": "GDP Growth",
                                "evidence": [
                                    {
                                        "tag": "Roosevelt 2017",
                                        "fullText": "Modeling a $1000/month UBI shows 12.56% GDP growth over 8 years.",
                                        "source": "Roosevelt Institute",
                                        "cite": "Roosevelt 2017",
                                        "fullCite": "Roosevelt Institute, 'Modeling the Macroeconomic Effects of a Universal Basic Income', 2017",
                                        "selectedTexts": ["12.56% GDP growth"],
                                        "sourceUrl": "https://example.com/roosevelt",
                                    },
                                ],
                            },
                        ],
                    },
                    {
                        "id": "b3",
                        "label": "Fiscal Unsustainability",
                        "claim": "UBI costs exceed federal budget capacity",
                        "side": "neg",
                        "arguments": [
                            {
                                "id": "a3",
                                "claim": "$12K/year x 250M adults = $3 trillion annually",
                                "warrant": "Exceeds entire discretionary budget",
                                "impact": "Unsustainable national debt",
                                "label": "Cost Analysis",
                                "evidence": [
                                    {
                                        "tag": "CBO 2023",
                                        "fullText": "Federal discretionary spending was $1.7 trillion in FY2023.",
                                        "source": "Congressional Budget Office",
                                        "cite": "CBO 2023",
                                        "fullCite": "Congressional Budget Office, 'Budget and Economic Outlook 2023-2033', 2023",
                                        "selectedTexts": ["$1.7 trillion"],
                                        "sourceUrl": "https://example.com/cbo",
                                    },
                                ],
                            },
                        ],
                    },
                ],
            },
        })
        await asyncio.sleep(0.02)

        # debate_ready
        await self._emit({
            "type": "debate_ready",
            "topic": self.config.topic,
            "humanSide": self.config.human_side,
            "speechOrder": IPDA_SPEECH_ORDER,
            "speechTimeLimits": SPEECH_TIME_LIMITS,
            "evidenceCards": [{"id": "ev1", "title": "UBI Finland Study", "source": "Kela 2020"}],
            "beliefTreeSummary": "Pro/con tree on UBI",
        })
        await asyncio.sleep(0.05)

        # Start first speech
        await self._advance_to_speech(0)

    async def _advance_to_speech(self, index: int) -> None:
        self._speech_index = index
        if index >= len(IPDA_SPEECH_ORDER):
            await self._start_judging()
            return

        speech_type = IPDA_SPEECH_ORDER[index]
        is_cx = IS_CX_SPEECH[speech_type]
        is_ai = self._is_ai_speech(speech_type)
        speaker = "ai" if is_ai else "human"

        # Set waiting flag BEFORE emitting turn signal, so if the test
        # responds immediately the callback sees the correct state.
        if not is_ai:
            self._waiting_for_human = True

        # Send turn signal
        await self._emit({
            "type": "turn_signal",
            "speechType": speech_type,
            "speaker": speaker,
            "isCx": is_cx,
            "timeLimit": SPEECH_TIME_LIMITS[speech_type],
            "speechIndex": index,
            "totalSpeeches": len(IPDA_SPEECH_ORDER),
            "status": "active",
        })
        await asyncio.sleep(0.02)

        if is_ai:
            await self._generate_ai_speech(speech_type, is_cx)

    async def _generate_ai_speech(self, speech_type: str, is_cx: bool) -> None:
        if is_cx:
            await self._run_cx(speech_type)
        else:
            # Progress events
            for stage in ["flow_study", "tactic_select", "skeleton_build", "speech_generate"]:
                await self._emit({
                    "type": "speech_progress",
                    "speechType": speech_type,
                    "stage": stage,
                    "message": f"Running {stage}...",
                })
                await asyncio.sleep(0.01)

            text = MOCK_SPEECHES.get(speech_type, f"Mock {speech_type} speech text.")
            wc = len(text.split())

            await self._emit({
                "type": "speech_text",
                "speechType": speech_type,
                "text": text,
                "wordCount": wc,
            })

            # Scoring
            if self.config.enable_scoring:
                await self._emit({
                    "type": "speech_scored",
                    "speechType": speech_type,
                    "score": 0.78,
                    "feedback": "Solid argumentation with clear evidence.",
                    "dimensions": [
                        {"name": "argument_quality", "score": 0.80, "maxScore": 1.0, "reasoning": "Clear claim-warrant-impact structure"},
                        {"name": "evidence_quality", "score": 0.75, "maxScore": 1.0, "reasoning": "Good sources but could use more recent data"},
                        {"name": "clash_engagement", "score": 0.78, "maxScore": 1.0, "reasoning": "Addresses key opposing arguments"},
                        {"name": "rhetoric", "score": 0.76, "maxScore": 1.0, "reasoning": "Effective delivery and organization"},
                    ],
                })

            # Flow update
            if self.config.enable_flow_study:
                await self._emit({
                    "type": "flow_update",
                    "speechType": speech_type,
                    "flow": {
                        "arguments": [
                            {
                                "id": "a1",
                                "label": "Cash Transfers",
                                "fullText": "Direct cash transfers reduce poverty by 40%",
                                "side": "aff",
                                "status": "standing",
                                "speechIntroduced": "AC",
                                "responses": [],
                                "warrant": "Finland and Kenya trials",
                                "impact": "Millions lifted out of poverty",
                                "evidenceTag": "Kela 2020",
                                "argumentCategory": "contention",
                                "attackType": "",
                                "attacks": [],
                                "parentId": None,
                            },
                        ],
                        "votingIssues": [
                            {
                                "id": "vi1",
                                "label": "Poverty Reduction",
                                "description": "Does UBI effectively reduce poverty?",
                                "affPosition": "Yes, 40% reduction shown in trials",
                                "negPosition": "Targeted programs are more effective",
                                "advantage": "aff",
                            },
                        ],
                        "clashPoints": [
                            {
                                "id": "cp1",
                                "label": "Fiscal Feasibility",
                                "affArgumentId": "a2",
                                "negArgumentId": "a3",
                                "status": "contested",
                            },
                        ],
                        "summary": f"Flow state after {speech_type}",
                        "standing": ["UBI reduces poverty"],
                        "attacked": [],
                        "dropped": [],
                    },
                })

            await asyncio.sleep(0.02)
            await self._advance_to_speech(self._speech_index + 1)

    async def _run_cx(self, speech_type: str) -> None:
        exchanges = CX_EXCHANGES.get(speech_type, [])
        for i, (q, a) in enumerate(exchanges):
            if self._is_ai_speech(speech_type):
                # AI is asking questions
                await self._emit({
                    "type": "cx_question_server",
                    "question": q,
                    "turnNumber": i,
                    "strategy": "probe_weakness",
                })
                await asyncio.sleep(0.02)
            else:
                # AI is answering
                await self._emit({
                    "type": "cx_answer_server",
                    "answer": a,
                    "questionRef": f"q{i}",
                })
                await asyncio.sleep(0.02)

        await asyncio.sleep(0.02)
        await self._advance_to_speech(self._speech_index + 1)

    async def _start_judging(self) -> None:
        await self._emit({
            "type": "judging_started",
            "message": "Judge is deliberating...",
            "estimatedSeconds": 10,
        })
        await asyncio.sleep(0.05)

        await self._emit({
            "type": "judge_result",
            "winner": "aff",
            "affScore": 82.5,
            "negScore": 78.0,
            "margin": "close",
            "decision": "The affirmative presented a more cohesive case with stronger evidence.",
            "votingIssues": ["fiscal sustainability", "poverty reduction", "labor effects"],
            "perSpeechFeedback": [
                {
                    "speechType": "AC",
                    "score": 0.80,
                    "maxScore": 1.0,
                    "feedback": "Strong opening with clear contentions.",
                    "strengths": ["Clear structure", "Strong evidence"],
                    "weaknesses": ["Could preempt negative arguments"],
                },
                {
                    "speechType": "NC",
                    "score": 0.78,
                    "maxScore": 1.0,
                    "feedback": "Good counter-arguments with fiscal analysis.",
                    "strengths": ["Fiscal analysis", "Multiple attack vectors"],
                    "weaknesses": ["Some assertions lack evidence"],
                },
            ],
        })

        # Mark complete
        await self._emit({
            "type": "turn_signal",
            "speechType": "2AR",
            "speaker": "human" if self.config.human_side == "aff" else "ai",
            "isCx": False,
            "timeLimit": 0,
            "speechIndex": 6,
            "totalSpeeches": 7,
            "status": "complete",
        })

    async def _on_client_message(self, data: Dict[str, Any]) -> None:
        """Handle messages from the SDK session (human actions)."""
        msg_type = data.get("type", "")

        if msg_type == "speech_end" and self._waiting_for_human:
            self._waiting_for_human = False
            speech_type = data.get("speechType", "")

            # Send coaching hint for next human speech if enabled
            if self.config.coaching_enabled:
                next_idx = self._speech_index + 1
                # Find next human speech
                for i in range(next_idx, len(IPDA_SPEECH_ORDER)):
                    st = IPDA_SPEECH_ORDER[i]
                    if not self._is_ai_speech(st) and not IS_CX_SPEECH[st]:
                        await self._emit({
                            "type": "coaching_hint",
                            "forSpeech": st,
                            "hints": [
                                {"type": "strategic", "text": "Focus on the dropped arguments."},
                                {"type": "evidence", "text": "Reference the Finland study data."},
                            ],
                        })
                        break

            await asyncio.sleep(0.02)
            await self._advance_to_speech(self._speech_index + 1)

        elif msg_type == "cx_question":
            # Human asking CX question — AI answers
            await self._emit({
                "type": "cx_answer_server",
                "answer": "That's a fair point, but our position accounts for that.",
                "questionRef": data.get("question", ""),
            })

        elif msg_type == "cx_answer":
            pass  # Human answering, no response needed

        elif msg_type == "cx_end":
            if self._waiting_for_human:
                self._waiting_for_human = False
                await self._advance_to_speech(self._speech_index + 1)

        elif msg_type == "prep_time_end":
            pass  # Acknowledged

        elif msg_type == "evidence_request":
            await self._emit({
                "type": "evidence_result",
                "query": data.get("query", ""),
                "cards": [
                    {"id": "ev2", "title": "UBI Economic Impact", "snippet": "GDP growth projected at 12%"},
                ],
                "totalResults": 1,
            })

        elif msg_type == "request_coaching":
            await self._emit({
                "type": "coaching_hint",
                "forSpeech": data.get("forSpeech", ""),
                "hints": [{"type": "strategic", "text": "Attack their weakest argument."}],
            })

    async def _emit(self, data: Dict[str, Any]) -> None:
        self._events_log.append(data)
        await self.channel.send_to_session(data)


# ---------------------------------------------------------------------------
# Recording event handler
# ---------------------------------------------------------------------------

class RecordingHandler(DebateEventHandler):
    """Captures all events for test assertions."""

    def __init__(self) -> None:
        self.events: List[Any] = []
        self.events_by_type: Dict[str, List[Any]] = {}
        self.timestamps: List[float] = []
        self._ready = asyncio.Event()
        self._complete = asyncio.Event()
        self._turn_signals: List[Any] = []
        self._human_turns: asyncio.Queue = asyncio.Queue()

    def _record(self, event: Any) -> None:
        self.events.append(event)
        t = event.type
        self.events_by_type.setdefault(t, []).append(event)
        self.timestamps.append(time.monotonic())

    async def on_debate_initializing(self, event):
        self._record(event)

    async def on_debate_ready(self, event):
        self._record(event)
        self._ready.set()

    async def on_turn_signal(self, event):
        self._record(event)
        self._turn_signals.append(event)
        if event.speaker == "human" and event.status == "active":
            await self._human_turns.put(event)
        if event.status == "complete":
            self._complete.set()

    async def on_speech_text(self, event):
        self._record(event)

    async def on_speech_progress(self, event):
        self._record(event)

    async def on_flow_update(self, event):
        self._record(event)

    async def on_coaching_hint(self, event):
        self._record(event)

    async def on_speech_scored(self, event):
        self._record(event)

    async def on_cx_question(self, event):
        self._record(event)

    async def on_cx_answer(self, event):
        self._record(event)

    async def on_evidence_result(self, event):
        self._record(event)

    async def on_judging_started(self, event):
        self._record(event)

    async def on_judge_result(self, event):
        self._record(event)

    async def on_error(self, event):
        self._record(event)

    async def on_belief_tree(self, event):
        self._record(event)

    async def on_unknown(self, event):
        self._record(event)

    async def on_disconnect(self, reason=""):
        pass

    async def wait_ready(self, timeout: float = 5.0) -> None:
        await asyncio.wait_for(self._ready.wait(), timeout)

    async def wait_complete(self, timeout: float = 30.0) -> None:
        await asyncio.wait_for(self._complete.wait(), timeout)

    async def wait_human_turn(self, timeout: float = 10.0):
        return await asyncio.wait_for(self._human_turns.get(), timeout)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def auto_play_remaining(session: ManagedDebateSession, handler: RecordingHandler) -> None:
    """Auto-play all remaining human turns until debate completes."""
    for _ in range(10):
        try:
            turn = await handler.wait_human_turn(timeout=3)
        except asyncio.TimeoutError:
            break
        st = turn.speech_type
        if IS_CX_SPEECH.get(st, False):
            await session.end_cx(st)
        else:
            await session.submit_speech(st, f"Auto speech for {st}", duration_seconds=60.0)
        await asyncio.sleep(0.05)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def debate_topic() -> str:
    return "Resolved: Universal basic income would benefit society."


@pytest.fixture
def aff_config(debate_topic) -> DebateConfig:
    return DebateConfig(topic=debate_topic, human_side="aff")


@pytest.fixture
def neg_config(debate_topic) -> DebateConfig:
    return DebateConfig(topic=debate_topic, human_side="neg")


@pytest.fixture
def channel() -> SimulatedDataChannel:
    return SimulatedDataChannel()


@pytest.fixture
def handler() -> RecordingHandler:
    return RecordingHandler()


@pytest_asyncio.fixture
async def aff_session(channel, handler, aff_config):
    """Session + agent where human is AFF."""
    participant = MockParticipant(channel)
    session = ManagedDebateSession(
        participant=participant,
        handler=handler,
        human_side="aff",
    )
    await session.connect()
    agent = SimulatedAgent(channel=channel, config=aff_config)
    return session, agent, handler


@pytest_asyncio.fixture
async def neg_session(channel, handler, neg_config):
    """Session + agent where human is NEG."""
    participant = MockParticipant(channel)
    session = ManagedDebateSession(
        participant=participant,
        handler=handler,
        human_side="neg",
    )
    await session.connect()
    agent = SimulatedAgent(channel=channel, config=neg_config)
    return session, agent, handler
