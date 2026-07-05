import subprocess
from pathlib import Path


class ProxyController:
    """Starts and stops the mitmproxy process that runs the pproxy engine.

    The proxy is launched as a child process — by default
    ``mitmdump -s <script>`` — where ``<script>`` is the ``intercept.py``
    that builds the addon via ``create_addon``. The controller owns the
    process handle and never blocks: ``start`` spawns, ``stop`` terminates.

    Args:
        script: Path to the mitmproxy addon script (``intercept.py``).
        command: The proxy executable. Defaults to ``mitmdump`` (headless,
            since the menu bar app is the UI). Use ``mitmweb`` for the web UI.
    """

    def __init__(self, script: str | Path, command: str = "mitmdump") -> None:
        self._script = str(script)
        self._command = command
        self._proc: subprocess.Popen[bytes] | None = None

    def is_running(self) -> bool:
        """Whether the proxy process is currently alive."""
        return self._proc is not None and self._proc.poll() is None

    def start(self) -> None:
        """Start the proxy if it is not already running.

        Idempotent — a no-op when the proxy is already up.

        Raises:
            FileNotFoundError: If the proxy executable is not installed.
        """
        if self.is_running():
            return
        self._proc = subprocess.Popen([self._command, "-s", self._script])

    def stop(self) -> None:
        """Stop the proxy, escalating to kill if it does not exit promptly.

        Idempotent — a no-op when the proxy is not running.
        """
        proc = self._proc
        self._proc = None
        if proc is None or proc.poll() is not None:
            return
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()

    def toggle(self) -> bool:
        """Start the proxy if stopped, stop it if running.

        Returns:
            The running state after toggling.
        """
        if self.is_running():
            self.stop()
        else:
            self.start()
        return self.is_running()
