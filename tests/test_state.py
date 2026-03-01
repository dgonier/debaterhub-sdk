"""Tests for DebateTurnTracker state machine."""

from debaterhub.state import DebateTurnTracker


class TestTurnTracker:
    def test_initial_state(self) -> None:
        t = DebateTurnTracker(human_side="aff")
        assert t.current_speech is None
        assert t.is_human_turn is False
        assert t.is_cx is False
        assert t.is_complete is False
        assert t.phase == "waiting"

    def test_aff_human_ac_turn(self) -> None:
        t = DebateTurnTracker(human_side="aff")
        t.update_from_turn_signal(speech_type="AC", speaker="human", status="active")
        assert t.current_speech == "AC"
        assert t.is_human_turn is True
        assert t.is_cx is False

    def test_aff_human_nc_is_not_human_turn(self) -> None:
        t = DebateTurnTracker(human_side="aff")
        t.update_from_turn_signal(speech_type="NC", speaker="ai", status="active")
        assert t.is_human_turn is False

    def test_neg_human_nc_turn(self) -> None:
        t = DebateTurnTracker(human_side="neg")
        t.update_from_turn_signal(speech_type="NC", speaker="human", status="active")
        assert t.is_human_turn is True

    def test_cx_detection(self) -> None:
        t = DebateTurnTracker(human_side="aff")
        t.update_from_turn_signal(speech_type="AC-CX", speaker="ai", status="active")
        assert t.is_cx is True
        # NEG is active during AC-CX
        assert t.is_human_turn is False

    def test_nc_cx_aff_is_active(self) -> None:
        t = DebateTurnTracker(human_side="aff")
        t.update_from_turn_signal(speech_type="NC-CX", speaker="human", status="active")
        assert t.is_cx is True
        assert t.is_human_turn is True  # AFF asks during NC-CX

    def test_complete_status(self) -> None:
        t = DebateTurnTracker(human_side="aff")
        t.update_from_turn_signal(speech_type="2AR", speaker="human", status="complete")
        assert t.is_complete is True

    def test_record_and_retrieve_transcripts(self) -> None:
        t = DebateTurnTracker(human_side="aff")
        t.record_speech("AC", "My first speech")
        t.record_speech("NC", "Opponent speech")
        assert t.transcripts == {"AC": "My first speech", "NC": "Opponent speech"}
        assert t.completed_speeches == ["AC", "NC"]

    def test_speech_side_lookup(self) -> None:
        t = DebateTurnTracker()
        assert t.get_side_for_speech("AC") == "aff"
        assert t.get_side_for_speech("NC") == "neg"
        assert t.get_side_for_speech("1AR") == "aff"
        assert t.get_side_for_speech("NR") == "neg"
        assert t.get_side_for_speech("2AR") == "aff"
        assert t.get_side_for_speech("AC-CX") == "neg"   # NEG asks during AC-CX
        assert t.get_side_for_speech("NC-CX") == "aff"   # AFF asks during NC-CX
