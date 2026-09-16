import pytest
from unittest.mock import AsyncMock, patch
import json

from app.event_handlers import handle_copyright_cleared

class MockMsg:
    def __init__(self, data: bytes):
        self.data = data
        self.ack = AsyncMock()
        self.nak = AsyncMock()

@pytest.mark.asyncio
async def test_handle_copyright_cleared_success():
    payload = {
        "upload_id": "test-upload-123",
        "blipp_id": "test-blipp-456",
        "decision": "cleared"
    }
    msg = MockMsg(data=json.dumps(payload).encode("utf-8"))

    mock_response = AsyncMock()
    mock_response.status_code = 200

    with patch("httpx.AsyncClient.patch", return_value=mock_response) as mock_patch:
        await handle_copyright_cleared(msg)
        
        mock_patch.assert_called_once()
        args, kwargs = mock_patch.call_args
        assert "content-ingest:8000/v1/uploads/test-upload-123/status" in args[0]
        assert kwargs["json"] == {"status": "published"}
        msg.ack.assert_called_once()
        msg.nak.assert_not_called()

@pytest.mark.asyncio
async def test_handle_copyright_cleared_http_error():
    payload = {
        "upload_id": "test-upload-123",
        "blipp_id": "test-blipp-456",
        "decision": "cleared"
    }
    msg = MockMsg(data=json.dumps(payload).encode("utf-8"))

    mock_response = AsyncMock()
    mock_response.status_code = 500

    with patch("httpx.AsyncClient.patch", return_value=mock_response):
        await handle_copyright_cleared(msg)
        
        msg.ack.assert_not_called()
        msg.nak.assert_called_once()
