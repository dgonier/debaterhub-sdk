"""Tests for DebateConfig validation and serialization."""

import pytest
from pydantic import ValidationError

from debaterhub.config import DebateConfig
from debaterhub.exceptions import ConfigValidationError


class TestDebateConfigValidation:
    def test_valid_aff(self, aff_config: DebateConfig) -> None:
        assert aff_config.human_side == "aff"
        assert aff_config.topic.startswith("Resolved:")

    def test_valid_neg(self, neg_config: DebateConfig) -> None:
        assert neg_config.human_side == "neg"

    def test_invalid_side_rejected(self) -> None:
        with pytest.raises(ValidationError):
            DebateConfig(topic="test", human_side="invalid")

    def test_empty_topic_rejected(self) -> None:
        with pytest.raises(ValidationError):
            DebateConfig(topic="", human_side="aff")

    def test_defaults(self) -> None:
        cfg = DebateConfig(topic="UBI is good")
        assert cfg.human_side == "aff"
        assert cfg.coaching_enabled is True
        assert cfg.evidence_enabled is True
        assert cfg.format == "ipda"


class TestDispatchMetadata:
    def test_contains_both_key_formats(self, aff_config: DebateConfig) -> None:
        meta = aff_config.to_dispatch_metadata()
        # snake_case
        assert meta["human_side"] == "aff"
        assert meta["coaching_enabled"] is True
        # camelCase
        assert meta["humanSide"] == "aff"
        assert meta["coachingEnabled"] is True

    def test_topic_present(self, aff_config: DebateConfig) -> None:
        meta = aff_config.to_dispatch_metadata()
        assert meta["topic"] == aff_config.topic

    def test_optional_fields_excluded_when_none(self) -> None:
        cfg = DebateConfig(topic="test")
        meta = cfg.to_dispatch_metadata()
        assert "ai_case_mode" not in meta
        assert "aiCaseMode" not in meta

    def test_optional_fields_included_when_set(self) -> None:
        cfg = DebateConfig(
            topic="test",
            ai_case_mode="reuse",
            ai_reuse_case_id="abc123",
        )
        meta = cfg.to_dispatch_metadata()
        assert meta["ai_case_mode"] == "reuse"
        assert meta["aiCaseMode"] == "reuse"
        assert meta["ai_reuse_case_id"] == "abc123"
        assert meta["aiReuseCaseId"] == "abc123"

    def test_neg_side_serialized(self, neg_config: DebateConfig) -> None:
        meta = neg_config.to_dispatch_metadata()
        assert meta["human_side"] == "neg"
        assert meta["humanSide"] == "neg"
