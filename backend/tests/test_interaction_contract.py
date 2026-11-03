import pytest
from pydantic import ValidationError

from app.modules.interactions.schemas import ImEnvelope, TextInteractionRequest


def test_text_validation_remains_available() -> None:
    assert TextInteractionRequest(text="hello").text == "hello"
    with pytest.raises(ValidationError):
        TextInteractionRequest(text="")


def test_websocket_envelope_is_versioned_and_rejects_invalid_sequence() -> None:
    envelope = ImEnvelope(
        type="interaction.subscribe",
        message_id="msg_test",
        request_id="req_test",
        interaction_id="interaction_test",
        sequence=3,
    )
    assert envelope.version == "1"
    assert envelope.sequence == 3
    with pytest.raises(ValidationError):
        ImEnvelope(
            type="interaction.subscribe",
            message_id="msg_test",
            request_id="req_test",
            sequence=-1,
        )
