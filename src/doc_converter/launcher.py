"""Windows-friendly local launcher for the Doc Converter web application."""

from __future__ import annotations

import argparse
import webbrowser
from collections.abc import Sequence
from threading import Timer

import uvicorn

from doc_converter.api import create_app


def application_url(port: int) -> str:
    """Return the loopback URL used by the single-process desktop launcher."""

    return f"http://127.0.0.1:{port}/"


def main(argv: Sequence[str] | None = None) -> None:
    """Start the local-only service and open the bundled browser interface."""

    parser = argparse.ArgumentParser(description="启动本地 Doc Converter")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error("端口必须介于 1 和 65535 之间。")

    if not args.no_browser:
        opener = Timer(0.6, webbrowser.open_new_tab, args=(application_url(args.port),))
        opener.daemon = True
        opener.start()
    uvicorn.run(create_app(), host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
