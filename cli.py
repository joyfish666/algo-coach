"""Single entry point of AlgoCoach.

Binds to 127.0.0.1 only (default port 8000), runs uvicorn in a single process
(rate-limit accounting and sync progress live in memory; multiple workers
would split state), and opens the browser once the server is ready.

Single-instance guard (closes the port-shift blind spot):
- ~/.algocoach/instance.lock is created with O_CREAT|O_EXCL so two concurrent
  launches cannot both claim it; it records pid + final port
- when the lock exists, a live recorded pid refuses startup while a dead one
  is taken over automatically (crash leftovers)
- before shifting away from an occupied preferred port, /api/status is probed:
  an answering coach instance refuses startup, any other occupant just shifts
- the shifted-to listener socket is bound once and handed to uvicorn, so no
  other process can claim the chosen port between discovery and startup
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import socket
import sys
import threading
import time
import urllib.request
import webbrowser

import uvicorn
from rich.console import Console
from rich.panel import Panel

import lc
from lc.config import INSTANCE_LOCK_NAME, app_dir
from lc.logutil import setup_logging

LOCK_FILE_NAME = INSTANCE_LOCK_NAME
LOG_FILE_NAME = "coach.log"
STILL_ACTIVE = 259


def lock_path():
    return app_dir() / LOCK_FILE_NAME


def _pid_alive(pid: int) -> bool:
    if not isinstance(pid, int) or pid <= 0:
        return False
    if sys.platform == "win32":
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return False
        exit_code = ctypes.c_ulong()
        ok = kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
        kernel32.CloseHandle(handle)
        return bool(ok) and exit_code.value == STILL_ACTIVE
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def acquire_instance_lock(port: int):
    """Atomically create the instance lock for the given port.

    Returns (True, "") on success, or (False, refusal message) when another
    live instance owns the lock. Stale locks from dead processes are removed
    and creation retried.
    """
    path = lock_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps({"pid": os.getpid(), "port": port}).encode("utf-8")
    while True:
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            try:
                info = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                info = {}
            if _pid_alive(info.get("pid")):
                return False, info
            try:
                path.unlink()
            except OSError:
                pass
            continue
        try:
            os.write(fd, payload)
        finally:
            os.close(fd)
        return True, ""


def release_instance_lock() -> None:
    try:
        lock_path().unlink()
    except OSError:
        pass


def probe_is_coach(host: str, port: int) -> bool:
    """True when something at host:port answers like our /api/status."""
    try:
        with urllib.request.urlopen(
            f"http://{host}:{port}/api/status", timeout=1.5
        ) as response:
            body = json.loads(response.read() or b"{}")
            return body.get("app") == "algocoach"
    except Exception:
        return False


def bind_free_socket(start: int, host: str = "127.0.0.1") -> socket.socket:
    """Bind a listener on the first free port at or after `start` and KEEP it.

    The socket stays open and is handed to uvicorn, closing the classic
    TOCTOU gap where find-then-release let another process claim the port
    between discovery and server startup.
    """
    for port in range(start, start + 100):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.bind((host, port))
            sock.listen(128)
            return sock
        except OSError:
            sock.close()
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

    # Wire the algocoach logger: always-on rotating file (support diagnostics,
    # see i18n "share the debug log" copy) plus --debug verbosity on console.
    log_dir = app_dir()
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        setup_logging(debug=args.debug, log_file=log_dir / LOG_FILE_NAME)
    except OSError:
        setup_logging(debug=args.debug)
        print(f"[coach] warning: could not write {log_dir / LOG_FILE_NAME}")

    if probe_is_coach(host, args.port):
        print(f"[coach] another AlgoCoach instance already answers at http://{host}:{args.port}")
        print("[coach] refusing to start a second one; open that URL in your browser instead.")
        return 1

    # fail at the door, not as a 500 on every API call later
    from lc.config import validate_environment

    try:
        validate_environment()
    except ValueError as exc:
        print(f"[coach] refusing to start: {exc}")
        print("[coach] fix or remove the environment variable above, then relaunch.")
        return 2

    try:
        sock = bind_free_socket(args.port, host)
    except RuntimeError:
        print(
            f"[coach] refusing to start: no free port found between "
            f"{args.port} and {args.port + 99}."
        )
        return 2
    port = sock.getsockname()[1]
    owned, existing = acquire_instance_lock(port)
    if not owned:
        sock.close()
        recorded = existing.get("port", port)
        print(
            f"[coach] refusing to start: another AlgoCoach instance "
            f"(pid {existing.get('pid', '?')}) already runs at http://{host}:{recorded}"
        )
        return 1

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
    try:
        # hand over the pre-bound listener so no other process can claim the
        # chosen port between discovery and startup
        server.run(sockets=[sock])
    finally:
        release_instance_lock()
    return 0


if __name__ == "__main__":
    sys.exit(main())
