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

LOG_FILE_NAME = "coach.log"
STILL_ACTIVE = 259
# how long acquire_instance_lock tolerates a lock file that exists but does
# not parse yet (the winner between O_EXCL create and its payload write)
_LOCK_GRACE_SECONDS = 2.0


def lock_path():
    return app_dir() / INSTANCE_LOCK_NAME


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


def _read_lock_info(path) -> dict | None:
    """Parse the lock payload; None means "created but not written yet".

    acquire_instance_lock creates the file with O_CREAT|O_EXCL and writes
    the pid payload only afterwards, so a second process launched in the
    same instant can legitimately observe a zero-byte file. Distinguishing
    that window from real garbage is what keeps two simultaneous launches
    from stripping each other's locks and both surviving.
    """
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    if not raw.strip():
        return None
    try:
        return json.loads(raw)
    except ValueError:
        return {}


def acquire_instance_lock(port: int):
    """Atomically create the instance lock for the given port.

    Returns (True, "") on success, or (False, refusal message) when another
    live instance owns the lock. Stale locks from dead processes are removed
    and creation retried; a just-created empty lock gets a short grace
    window because its writer may simply not have flushed the payload yet.
    """
    path = lock_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps({"pid": os.getpid(), "port": port}).encode("utf-8")
    deadline = time.monotonic() + _LOCK_GRACE_SECONDS
    while True:
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            info = _read_lock_info(path)
            if _pid_alive(info.get("pid")):
                return False, info
            if info is None and time.monotonic() < deadline:
                time.sleep(0.05)
                continue
            try:
                path.unlink()
            except OSError:
                if time.monotonic() < deadline:
                    time.sleep(0.05)
                    continue
                # cannot read OR recycle the lock: refuse rather than risk
                # becoming a second live instance
                return False, info or {}
            continue
        try:
            os.write(fd, payload)
        finally:
            os.close(fd)
        return True, ""


def release_instance_lock() -> None:
    """Remove the lock file only when it still records our own pid.

    Unlinking unconditionally deleted the *successor's* lock after a
    crash-and-takeover, reopening the double-instance window the guard
    exists to close.
    """
    path = lock_path()
    info = _read_lock_info(path)
    if isinstance(info, dict) and info.get("pid") == os.getpid():
        try:
            path.unlink()
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


def start_idle_exit_watchdog(server, minutes: float) -> None:
    """Shut down once the web UI goes quiet.

    Every open tab pings /api/heartbeat; when no beat arrives for `minutes`,
    the last tab is gone and a headless server has no reason to keep running
    (double-click launches especially - the user asked the window to close
    with the site). A running problem sync holds the exit: closing the tab
    mid-sync must not truncate a 2-3 minute full rebuild.
    """
    from server import state

    def watch():
        deadline = minutes * 60
        while not server.should_exit:
            time.sleep(5)
            if state.seconds_since_heartbeat() < deadline:
                continue
            if state.sync_running():
                continue
            print(
                f"[coach] no web UI heartbeat for {minutes:g} min - shutting down"
            )
            server.should_exit = True
            return

    threading.Thread(target=watch, name="idle-exit-watchdog", daemon=True).start()


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
    parser.add_argument(
        "--idle-exit",
        type=float,
        default=0.0,
        metavar="MINUTES",
        help="shut down automatically after N minutes without a web-UI "
        "heartbeat, so closing the last browser tab retires the server "
        "(0 disables; the bundled start.bat passes 2)",
    )
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
        url = f"http://{host}:{args.port}"
        print(f"[coach] AlgoCoach already runs at {url}")
        if not args.no_browser:
            # double-clicking the launcher again must end with the site open,
            # not a second server and not an error window: adopt the running
            # instance (its idle-exit clock also resets once the browser
            # heartbeats again)
            print("[coach] opening it in your browser instead of starting a second instance.")
            webbrowser.open(url)
            return 0
        print("[coach] refusing to start a second one; open that URL in your browser.")
        return 1

    # fail at the door, not as a 500 on every API call later
    from lc.config import config_path, effective_config, validate_environment

    try:
        validate_environment()
    except ValueError as exc:
        print(f"[coach] refusing to start: {exc}")
        print("[coach] fix or remove the environment variable above, then relaunch.")
        return 2

    # same door for the config file: a corrupt hand-edited or future-schema
    # config.toml used to start fine (banner printed) and then explode as a
    # TOMLDecodeError inside effective_config() on every endpoint
    try:
        effective_config()
    except (OSError, ValueError) as exc:
        print(f"[coach] refusing to start: config file could not be read: {exc}")
        print(f"[coach] fix or remove {config_path()}, then relaunch.")
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
        # the probe above only knows the preferred port; a port-shifted
        # survivor is recorded in the lock, so open its actual URL
        recorded = existing.get("port", port)
        url = f"http://{host}:{recorded}"
        print(
            f"[coach] another AlgoCoach instance (pid {existing.get('pid', '?')}) "
            f"already runs at {url}"
        )
        if not args.no_browser:
            print("[coach] opening it in your browser instead of starting a second instance.")
            webbrowser.open(url)
            return 0
        print("[coach] refusing to start a second one.")
        return 1

    url = f"http://{host}:{port}"
    config = uvicorn.Config(
        "server.app:app",
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

    # the idle clock starts at process start: the auto-opened browser begins
    # heartbeating within seconds, and a tab that never opens lets the server
    # retire after the deadline instead of lingering headless forever
    if args.idle_exit > 0:
        start_idle_exit_watchdog(server, args.idle_exit)

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
