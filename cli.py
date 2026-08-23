"""Single entry point of AlgoCoach.

Binds to 127.0.0.1 only (default port 8000, auto-incremented when occupied),
starts uvicorn in a single process (rate-limit accounting and sync progress
live in memory; multiple workers would split state), and opens the browser
once the server is ready.
"""

import argparse
import socket
import sys
import threading
import time
import webbrowser

import uvicorn
from rich.panel import Panel
from rich.console import Console

import lc


def find_free_port(start, host="127.0.0.1"):
    for port in range(start, start + 100):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind((host, port))
                return port
            except OSError:
                continue
    raise RuntimeError(f"no free port found starting from {start}")


def open_browser_when_ready(server, url):
    while not server.started:
        if server.should_exit:
            return
        time.sleep(0.1)
    webbrowser.open(url)


def print_banner(url):
    console = Console()
    console.print(
        Panel.fit(
            f"[bold blue]{url}[/bold blue]",
            title=f"[bold]AlgoCoach v{lc.__version__}[/bold]",
            subtitle="press Ctrl+C to stop",
        )
    )


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="coach",
        description=f"AlgoCoach v{lc.__version__}: local LeetCode practice workbench",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="preferred port (auto-increments when occupied, default 8000)",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="do not open the browser automatically",
    )
    parser.add_argument("--debug", action="store_true", help="verbose logging")
    args = parser.parse_args(argv)

    host = "127.0.0.1"
    port = find_free_port(args.port)
    url = f"http://{host}:{port}"

    config = uvicorn.Config(
        "server.api:app",
        host=host,
        port=port,
        log_level="debug" if args.debug else "info",
    )
    server = uvicorn.Server(config)

    if not args.no_browser:
        threading.Thread(
            target=open_browser_when_ready,
            args=(server, url),
            daemon=True,
        ).start()

    print_banner(url)
    server.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
