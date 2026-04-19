# tests/host/test_weather.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'host'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'host', 'producers'))

from unittest.mock import patch, MagicMock
from weather import _fetch, _parse


def test_parse_strips_city_name():
    assert _parse("Cairo: ⛅ +28°C") == "⛅ +28°C"


def test_parse_no_colon_returns_as_is():
    assert _parse("⛅ +28°C") == "⛅ +28°C"


def test_parse_truncates_to_20_chars():
    long = "A" * 30
    assert len(_parse(long)) <= 20


def test_fetch_returns_parsed_text():
    mock_resp = MagicMock()
    mock_resp.text = "Cairo: ⛅ +28°C\n"
    mock_resp.raise_for_status = lambda: None
    with patch('weather.requests.get', return_value=mock_resp):
        result = _fetch()
    assert result == "⛅ +28°C"


def test_fetch_returns_none_on_network_error():
    with patch('weather.requests.get', side_effect=Exception("timeout")):
        result = _fetch()
    assert result is None
