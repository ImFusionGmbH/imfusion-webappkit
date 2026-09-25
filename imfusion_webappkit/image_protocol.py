"""
Image serialization/deserialization protocol for WebSocket communication.

Uses the ImFusion .imf file format for serialization, which preserves all
metadata (spacing, matrix, orientation, etc.) natively.
"""

import json
import base64
import imfusion
import logging
import tempfile
import os
from typing import Dict, Any, Tuple, List

logger = logging.getLogger(__name__)


class ImageProtocol:
    """Handle serialization and deserialization of ImFusion data using .imf format."""

    @staticmethod
    def serialize_data_list(data_list: List[Any]) -> Dict[str, Any]:
        """
        Serialize a list of ImFusion data items as an .imf file buffer.

        The .imf format can contain multiple data items and preserves all metadata.

        Args:
            data_list: List of ImFusion data items to serialize

        Returns:
            Dictionary containing:
                - buffer: base64-encoded .imf file
                - format: 'imf' to indicate the format
        """
        if not data_list:
            raise ValueError("Cannot serialize empty data list")

        imf_bytes = ImageProtocol.serialize_data_list_bytes(data_list)
        return {"format": "imf", "buffer": base64.b64encode(imf_bytes).decode("utf-8")}

    @staticmethod
    def serialize_data_list_bytes(data_list: List[Any]) -> bytes:
        """Serialize ImFusion data items to raw .imf bytes."""
        if not data_list:
            raise ValueError("Cannot serialize empty data list")

        # Create a temporary file to save the .imf
        with tempfile.NamedTemporaryFile(suffix=".imf", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            # Save the data list as .imf using ImFusion's native export
            logger.info(
                f"Exporting {len(data_list)} data item(s) to .imf format: {tmp_path}"
            )
            imfusion.save(data_list, tmp_path)

            # Read the .imf file as bytes
            with open(tmp_path, "rb") as f:
                imf_bytes = f.read()

            logger.info(
                f"IMF file size: {len(imf_bytes)} bytes ({len(imf_bytes) / 1024:.2f} KB)"
            )

            return imf_bytes

        finally:
            # Clean up temporary file
            try:
                os.unlink(tmp_path)
            except Exception as e:
                logger.warning(f"Could not delete temporary file {tmp_path}: {e}")

    @staticmethod
    def deserialize_data_list(data: Dict[str, Any]) -> List[Any]:
        """
        Deserialize .imf file buffer to a list of ImFusion data items.

        Args:
            data: Dictionary containing buffer in .imf format

        Returns:
            List of ImFusion data items
        """
        return ImageProtocol.deserialize_data_list_bytes(
            base64.b64decode(data["buffer"])
        )

    @staticmethod
    def deserialize_data_list_bytes(file_bytes: bytes) -> List[Any]:
        """Deserialize raw .imf bytes to ImFusion data items."""
        logger.info(
            f"Received .imf buffer: {len(file_bytes)} bytes "
            f"({len(file_bytes) / 1024:.2f} KB)"
        )

        with tempfile.NamedTemporaryFile(suffix=".imf", delete=False) as tmp:
            tmp_path = tmp.name
            tmp.write(file_bytes)

        try:
            logger.info(f"Loading .imf from temporary file: {tmp_path}")
            data_list = imfusion.load(tmp_path)
            logger.info(f"Successfully loaded {len(data_list)} data item(s)")
            return list(data_list)
        except Exception as e:
            logger.error(f"Error deserializing data list: {e}", exc_info=True)
            raise
        finally:
            try:
                os.unlink(tmp_path)
            except Exception as e:
                logger.warning(f"Could not delete temporary file {tmp_path}: {e}")

    @staticmethod
    def create_binary_message(msg_type: str, payload: bytes, data: Any = None) -> bytes:
        """Frame raw bytes with a length-prefixed JSON message header."""
        header = json.dumps(
            {"type": msg_type, "data": data or {}},
            separators=(",", ":"),
        ).encode("utf-8")
        return len(header).to_bytes(4, "big") + header + payload

    @staticmethod
    def parse_binary_message(message: bytes) -> Tuple[str, Any, bytes]:
        """Parse a length-prefixed JSON header followed by raw payload bytes."""
        if len(message) < 4:
            raise ValueError("Binary message is missing its header length")
        header_length = int.from_bytes(message[:4], "big")
        payload_offset = 4 + header_length
        if header_length == 0 or payload_offset > len(message):
            raise ValueError("Binary message has an invalid header length")
        header = json.loads(message[4:payload_offset].decode("utf-8"))
        msg_type = header.get("type")
        if not isinstance(msg_type, str) or not msg_type:
            raise ValueError("Binary message is missing its type")
        return msg_type, header.get("data") or {}, message[payload_offset:]

    @staticmethod
    def parse_message(message: str) -> Tuple[str, Any]:
        """
        Parse a JSON message from WebSocket.

        Args:
            message: JSON string

        Returns:
            Tuple of (message_type, data)
        """
        parsed = json.loads(message)
        return parsed.get("type"), parsed.get("data")
