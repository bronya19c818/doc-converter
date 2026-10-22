"""Windows-friendly local launcher for the Doc Converter web application."""

from __future__ import annotations

import argparse
import json
import socket
import webbrowser
from collections.abc import Sequence
from threading import Thread
from time import monotonic, sleep
from urllib.error import URLError
from urllib.request import ProxyHandler, build_opener

import uvicorn

from doc_converter.api import create_app


def application_url(port: int) -> str:
    """Return the loopback URL used by the single-process desktop launcher."""
    return f"http://127.0.0.1:{port}/"


def _application_ready(url: str) -> bool:
    try:
        # Loopback readiness must not depend on the machine's proxy settings.
        with build_opener(ProxyHandler({})).open(url + "health", timeout=0.5) as response:
            payload = json.load(response)
        return payload == {"status": "ok", "processing": "local-only"}
    except (OSError, URLError, ValueError):
        return False


def _open_when_ready(url: str) -> None:
    deadline = monotonic() + 60
    while monotonic() < deadline:
        if _application_ready(url):
            if not webbrowser.open(url):
                print(f"请在浏览器中打开：{url}", flush=True)
            return
        sleep(0.2)
    print(f"浏览器未自动打开，服务就绪后请访问：{url}", flush=True)


def main(argv: Sequence[str] | None = None) -> None:
    """Start one local service and open its frontend once it responds."""
    parser = argparse.ArgumentParser(description="启动本地 Doc Converter")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error("端口必须介于 1 和 65535 之间。")

    url = application_url(args.port)
    if _application_ready(url):
        print(f"Doc Converter 已在运行：{url}", flush=True)
        if not args.no_browser:
            _open_when_ready(url)
        return
    try:
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", args.port))
    except OSError:
        parser.exit(1, f"端口 {args.port} 已被其他程序占用。请使用 --port 指定其他端口。\n")

    app = create_app()
    print(f"Doc Converter：{url}\n关闭此窗口或按 Ctrl+C 停止服务。", flush=True)
    if not args.no_browser:
        Thread(target=_open_when_ready, args=(url,), daemon=True).start()
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
