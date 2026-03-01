"""Tests for wire message parsing and key normalization."""

import json

import pytest

from debaterhub.events import (
    DebateEvent,
    DebateReadyEvent,
    ErrorEvent,
    TurnSignalEvent,
    event_from_dict,
)
from debaterhub.exceptions import ProtocolError
from debaterhub.protocol import parse_server_message


class TestParseServerMessage:
    def test_basic_parse(self) -> None:
        raw = json.dumps({"type": "turn_signal", "speechType": "AC", "speaker": "human"}).encode()
        msg = parse_server_message(raw)
        assert msg["type"] == "turn_signal"
        assert msg["speech_type"] == "AC"  # snake_case alias added
        assert msg["speechType"] == "AC"   # original preserved

    def test_camel_to_snake_normalisation(self) -> None:
        raw = json.dumps({"type": "debate_ready", "humanSide": "aff", "speechOrder": ["AC"]}).encode()
        msg = parse_server_message(raw)
        assert msg["human_side"] == "aff"
        assert msg["speech_order"] == ["AC"]

    def test_speech_type_underscore_normalised(self) -> None:
        """Agent sometimes sends AC_CX instead of AC-CX."""
        raw = json.dumps({"type": "turn_signal", "speechType": "AC_CX", "speaker": "ai"}).encode()
        msg = parse_server_message(raw)
        assert msg["speech_type"] == "AC-CX"

    def test_missing_type_raises(self) -> None:
        raw = json.dumps({"speechType": "AC"}).encode()
        with pytest.raises(ProtocolError, match="missing 'type'"):
            parse_server_message(raw)

    def test_invalid_json_raises(self) -> None:
        with pytest.raises(ProtocolError, match="Invalid JSON"):
            parse_server_message(b"not json")

    def test_non_object_raises(self) -> None:
        with pytest.raises(ProtocolError, match="Expected JSON object"):
            parse_server_message(b'"just a string"')

    def test_unknown_fields_tolerated(self) -> None:
        raw = json.dumps({"type": "turn_signal", "speaker": "ai", "futureField": 42}).encode()
        msg = parse_server_message(raw)
        assert msg["futureField"] == 42


class TestEventFromDict:
    def test_turn_signal(self) -> None:
        data = {"type": "turn_signal", "speech_type": "NC", "speaker": "ai", "is_cx": False, "time_limit": 360}
        event = event_from_dict(data)
        assert isinstance(event, TurnSignalEvent)
        assert event.speech_type == "NC"
        assert event.speaker == "ai"

    def test_error_event(self) -> None:
        data = {"type": "error", "message": "oops", "code": "AGENT_ERROR", "recoverable": False}
        event = event_from_dict(data)
        assert isinstance(event, ErrorEvent)
        assert event.message == "oops"
        assert event.recoverable is False

    def test_unknown_type_falls_back(self) -> None:
        data = {"type": "some_future_event", "data": 123}
        event = event_from_dict(data)
        assert isinstance(event, DebateEvent)
        assert event.type == "some_future_event"

    def test_debate_ready(self) -> None:
        data = {
            "type": "debate_ready",
            "topic": "UBI",
            "human_side": "aff",
            "speech_order": ["AC", "AC-CX", "NC"],
            "speech_time_limits": {"AC": 300},
        }
        event = event_from_dict(data)
        assert isinstance(event, DebateReadyEvent)
        assert event.speech_order == ["AC", "AC-CX", "NC"]

    def test_raw_preserved(self) -> None:
        data = {"type": "error", "message": "test", "extra_field": "xyz"}
        event = event_from_dict(data)
        assert event.raw["extra_field"] == "xyz"
