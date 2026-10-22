import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from desktop_launcher import wait_for_backend


def test_wait_for_backend_success():
    with patch("httpx.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_get.return_value = mock_resp

        ready = wait_for_backend(timeout=1.0)
        assert ready is True


def test_wait_for_backend_timeout():
    with patch("httpx.get", side_effect=Exception("Connection refused")):
        ready = wait_for_backend(timeout=0.5)
        assert ready is False
