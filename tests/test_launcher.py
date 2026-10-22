import runpy
import socket
import sys


def test_application_url_uses_localhost_and_requested_port() -> None:
    module = runpy.run_module("doc_converter.launcher", run_name="launcher_test")
    assert module["application_url"](8765) == "http://127.0.0.1:8765/"


def test_running_launcher_module_invokes_local_server(monkeypatch) -> None:
    calls = []
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    monkeypatch.setattr(sys, "argv", ["doc_converter.launcher", "--no-browser", "--port", str(port)])
    monkeypatch.setattr("uvicorn.run", lambda *args, **kwargs: calls.append((args, kwargs)))

    runpy.run_module("doc_converter.launcher", run_name="__main__")

    assert calls[0][1]["host"] == "127.0.0.1"
    assert calls[0][1]["port"] == port
