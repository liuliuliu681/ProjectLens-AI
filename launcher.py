"""Windows desktop launcher for the bundled Streamlit application."""

import os
import socket
import threading
import time
import urllib.request
import webbrowser

from core.paths import resource_root


def available_port(preferred: int = 8501) -> int:
    """Use 8501 when free, otherwise ask Windows for a local free port."""
    with socket.socket() as probe:
        try:
            probe.bind(("127.0.0.1", preferred))
        except OSError:
            probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def open_when_ready(port: int, timeout: float = 30.0) -> None:
    url = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url + "/_stcore/health", timeout=1) as response:
                if response.status == 200:
                    webbrowser.open(url)
                    return
        except OSError:
            pass
        time.sleep(0.3)


def main() -> None:
    from streamlit.web import bootstrap

    os.environ["STREAMLIT_SERVER_HEADLESS"] = "true"
    os.environ["STREAMLIT_BROWSER_GATHER_USAGE_STATS"] = "false"
    port = available_port()
    threading.Thread(target=open_when_ready, args=(port,), daemon=True).start()
    options = {
        "global.developmentMode": False,
        "server.address": "127.0.0.1", "server.port": port,
        "server.headless": True, "server.maxUploadSize": 10,
        "browser.gatherUsageStats": False,
    }
    bootstrap.load_config_options(options)
    bootstrap.run(str(resource_root() / "app.py"), False, [], options)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        import ctypes
        message = f"ProjectLens AI 启动失败：{type(exc).__name__}。请检查程序目录权限。"
        ctypes.windll.user32.MessageBoxW(None, message, "ProjectLens AI", 0x10)
        raise
