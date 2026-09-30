import socket
import sys
from pathlib import Path

from core.paths import env_path, resource_root, writable_root
from launcher import available_port, open_when_ready


def test_source_paths():
    assert resource_root() == Path(__file__).resolve().parent.parent
    assert writable_root() == resource_root()
    assert env_path() == resource_root() / ".env"


def test_frozen_paths(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path / "_internal"), raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "ProjectLensAI.exe"))
    assert resource_root() == tmp_path / "_internal"
    assert env_path() == tmp_path / ".env"


def test_occupied_port_chooses_other_port():
    with socket.socket() as held:
        held.bind(("127.0.0.1", 0))
        port = held.getsockname()[1]
        assert available_port(port) != port


def test_launcher_opens_browser_after_health_check(monkeypatch):
    opened = []

    class Healthy:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr("launcher.urllib.request.urlopen", lambda url, timeout: Healthy())
    monkeypatch.setattr("launcher.webbrowser.open", opened.append)
    open_when_ready(8501, timeout=1)
    assert opened == ["http://127.0.0.1:8501"]
