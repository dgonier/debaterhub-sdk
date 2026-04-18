"""Tests for the client-side format registry."""

import pytest

from debaterhub import DebateConfig, DebateTurnTracker, get_format_spec
from debaterhub.exceptions import ConfigValidationError


def test_ipda_spec_round_trip():
    spec = get_format_spec("ipda")
    assert spec.speech_ids == ["AC", "AC-CX", "NC", "NC-CX", "1AR", "NR", "2AR"]
    assert spec.speech_time_limits["AC"] == 300


def test_ld_spec():
    spec = get_format_spec("ld")
    assert spec.speech_time_limits["AC"] == 360
    assert spec.speech_time_limits["NC"] == 420
    assert spec.speech_time_limits["1AR"] == 240


def test_pf_spec_length():
    spec = get_format_spec("pf")
    assert len(spec.speech_order) == 11
    assert spec.first_speaker_configurable


def test_unknown_format_from_spec():
    with pytest.raises(ValueError):
        get_format_spec("policy")


def test_debate_config_validates_format():
    DebateConfig(topic="x", format="ipda")
    DebateConfig(topic="x", format="ld")
    DebateConfig(topic="x", format="pf")
    DebateConfig(topic="x", format="PF")  # case-insensitive via validator lowercase
    with pytest.raises(Exception):
        DebateConfig(topic="x", format="parliamentary")


def test_tracker_respects_format():
    t = DebateTurnTracker(human_side="aff", format="pf")
    assert t.format_spec.speech_ids[0] == "PF-AC"

    t.update_from_turn_signal(speech_type="PF-CF1", speaker="human")
    # Crossfire: human is active regardless of side
    assert t.is_human_turn is True
    assert t.is_cx is True

    t2 = DebateTurnTracker(human_side="neg", format="pf")
    t2.update_from_turn_signal(speech_type="PF-CF1", speaker="ai")
    assert t2.is_human_turn is True


def test_tracker_ipda_default_unchanged():
    t = DebateTurnTracker(human_side="aff")  # default format=ipda
    t.update_from_turn_signal(speech_type="AC", speaker="human")
    assert t.is_human_turn is True
    t.update_from_turn_signal(speech_type="NC", speaker="ai")
    assert t.is_human_turn is False


def test_legacy_constants_still_work():
    from debaterhub import IPDA_SPEECH_ORDER, SPEECH_TIME_LIMITS
    assert IPDA_SPEECH_ORDER == ["AC", "AC-CX", "NC", "NC-CX", "1AR", "NR", "2AR"]
    assert SPEECH_TIME_LIMITS["AC"] == 300


def test_dispatch_metadata_includes_format():
    cfg = DebateConfig(topic="x", format="ld")
    meta = cfg.to_dispatch_metadata()
    assert meta["format"] == "ld"


def test_pf_first_speaker_in_metadata():
    cfg = DebateConfig(topic="x", format="pf", pf_first_speaker="neg")
    meta = cfg.to_dispatch_metadata()
    assert meta["pf_first_speaker"] == "neg"
    assert meta["pfFirstSpeaker"] == "neg"
