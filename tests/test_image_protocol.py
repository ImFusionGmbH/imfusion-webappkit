"""Tests for image transport framing."""

import pytest

from imfusion_webappkit.image_protocol import ImageProtocol


def test_binary_message_round_trip():
    payload = bytes(range(256)) * 4

    message = ImageProtocol.create_binary_message(
        "data_update",
        payload,
        {"format": "imf", "index": 2, "name": "Updated"},
    )

    assert ImageProtocol.parse_binary_message(message) == (
        "data_update",
        {"format": "imf", "index": 2, "name": "Updated"},
        payload,
    )


@pytest.mark.parametrize("message", [b"", b"\0\0\0", b"\0\0\0\x08{}"])
def test_binary_message_rejects_invalid_header(message):
    with pytest.raises(ValueError):
        ImageProtocol.parse_binary_message(message)
