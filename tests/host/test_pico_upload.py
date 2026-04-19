# tests/host/test_pico_upload.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'host'))

from unittest.mock import patch, MagicMock, call
from pico_upload import upload, _build_mpremote_args


def test_build_mpremote_args_single_file():
    args = _build_mpremote_args(["main.py"])
    assert args == ["mpremote", "cp", "main.py", ":"]


def test_build_mpremote_args_multiple_files():
    args = _build_mpremote_args(["main.py", "companion.py"])
    assert args == ["mpremote", "cp", "main.py", ":", "+", "cp", "companion.py", ":"]


def test_upload_notifies_daemon_before_mpremote():
    call_order = []

    mock_sock = MagicMock()
    mock_sock.recv.return_value = b"OK\n"

    def fake_connect(path):
        call_order.append("connect")

    def fake_run(args):
        call_order.append("mpremote")
        return MagicMock(returncode=0)

    mock_sock.connect.side_effect = fake_connect

    with patch('pico_upload.socket.socket', return_value=mock_sock), \
         patch('pico_upload.subprocess.run', side_effect=fake_run):
        upload(["main.py"])

    assert call_order == ["connect", "mpremote"]


def test_upload_proceeds_without_daemon():
    mock_sock = MagicMock()
    mock_sock.connect.side_effect = Exception("no daemon")

    with patch('pico_upload.socket.socket', return_value=mock_sock), \
         patch('pico_upload.subprocess.run', return_value=MagicMock(returncode=0)) as mock_run:
        result = upload(["main.py"])

    assert result == 0
    mock_run.assert_called_once()


def test_upload_returns_mpremote_exit_code():
    mock_sock = MagicMock()
    mock_sock.recv.return_value = b"OK\n"

    with patch('pico_upload.socket.socket', return_value=mock_sock), \
         patch('pico_upload.subprocess.run', return_value=MagicMock(returncode=1)):
        result = upload(["main.py"])

    assert result == 1
