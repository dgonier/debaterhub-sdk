"""Shared test fixtures for debaterhub-sdk."""

import pytest

from debaterhub.config import DebateConfig


@pytest.fixture
def aff_config() -> DebateConfig:
    return DebateConfig(topic="Resolved: AI does more good than harm.", human_side="aff")


@pytest.fixture
def neg_config() -> DebateConfig:
    return DebateConfig(topic="Resolved: AI does more good than harm.", human_side="neg")
