import os
import signal
import subprocess
import time
from pathlib import Path

from tray.paths import runtime_dir


def _alive(pid: int) -> bool:
    """Whether a process with ``pid`` currently exists."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


class ProxyDaemon:
    """Starts and stops the proxy as a *detached* process, tracked by pidfile.

    Unlike an in-memory controller, this survives across separate
    invocations — the SwiftBar plugin runs, exits, and runs again, so the
    running state must live on disk. ``start`` spawns ``mitmdump`` in its
    own session (so it outlives the caller) and records its pid; ``stop``
    reads that pid back and terminates the process group.

    Args:
        script: Path to the mitmproxy addon script (``intercept.py``).
        command: Proxy executable. Defaults to ``mitmdump``.
        pidfile: Where to record the running pid. Defaults to
            ``<runtime_dir>/proxy.pid``.
        logfile: Where the proxy's output is written. Defaults to
            ``<runtime_dir>/proxy.log``.
    """

    def __init__(
        self,
        script: str | Path,
        command: str = "mitmdump",
        pidfile: str | Path | None = None,
        logfile: str | Path | None = None,
    ) -> None:
        self._script = str(script)
        self._command = command
        rt = runtime_dir()
        self._pidfile = Path(pidfile) if pidfile else rt / "proxy.pid"
        self._logfile = Path(logfile) if logfile else rt / "proxy.log"

    @property
    def logfile(self) -> Path:
        return self._logfile

    def is_running(self) -> bool:
        """Whether the tracked proxy process is alive."""
        pid = self._read_pid()
        return pid is not None and _alive(pid)

    def start(self) -> None:
        """Spawn the proxy detached if it is not already running.

        Idempotent. The child is placed in a new session so it is not
        killed when the launching process (the plugin) exits.

        Raises:
            FileNotFoundError: If the proxy executable is not installed.
        """
        if self.is_running():
            return
        self._pidfile.parent.mkdir(parents=True, exist_ok=True)
        log = open(self._logfile, "ab")
        try:
            proc = subprocess.Popen(
                [self._command, "-s", self._script],
                stdout=log,
                stderr=log,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
            )
        finally:
            log.close()
        self._write_pid(proc.pid)

    def stop(self) -> None:
        """Terminate the proxy, escalating to SIGKILL if it lingers.

        Idempotent — clears the pidfile and returns if nothing is running.
        """
        pid = self._read_pid()
        self._clear_pid()
        if pid is None or not _alive(pid):
            return
        self._signal_group(pid, signal.SIGTERM)
        for _ in range(50):  # up to ~5s
            if not _alive(pid):
                return
            time.sleep(0.1)
        self._signal_group(pid, signal.SIGKILL)

    def toggle(self) -> bool:
        """Start if stopped, stop if running; return the state after."""
        if self.is_running():
            self.stop()
        else:
            self.start()
        return self.is_running()

    # ── pidfile / signals ──────────────────────────────────

    @staticmethod
    def _signal_group(pid: int, sig: int) -> None:
        try:
            os.killpg(os.getpgid(pid), sig)
        except (ProcessLookupError, PermissionError):
            pass

    def _read_pid(self) -> int | None:
        try:
            return int(self._pidfile.read_text().strip())
        except (FileNotFoundError, ValueError):
            return None

    def _write_pid(self, pid: int) -> None:
        self._pidfile.write_text(str(pid))

    def _clear_pid(self) -> None:
        self._pidfile.unlink(missing_ok=True)
