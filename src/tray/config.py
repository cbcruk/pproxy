import json
import os
from pathlib import Path

from tray.paths import config_path

DEFAULT_EDITOR = "code"
"""The editor command used when nothing else is configured (VS Code)."""

BACKENDS = ("mitmproxy", "node")
"""The proxies pproxy can drive. Both read the same rules file."""

DEFAULT_BACKEND = "mitmproxy"
"""The proxy started when nothing else is configured."""


class Config:
    """Persisted app settings — the editor, and which proxy to start.

    Every setting resolves in the same order of precedence:

        1. an environment variable (``PPROXY_EDITOR``, ``PPROXY_BACKEND``,
           ``PPROXY_COMMAND``),
        2. the matching key in the config file,
        3. the built-in default.

    A malformed or unreadable config file is treated as empty rather than
    raising, so a bad file never stops the app from starting.

    Args:
        path: Config file location. Defaults to
            ``~/.config/pproxy/config.json`` (honoring ``XDG_CONFIG_HOME``).
    """

    def __init__(self, path: str | Path | None = None) -> None:
        self._path = Path(path) if path is not None else config_path()
        self._data = self._read()

    def _read(self) -> dict:
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return {}
        return data if isinstance(data, dict) else {}

    @property
    def path(self) -> Path:
        return self._path

    @property
    def editor(self) -> str:
        """The editor command to open the rules file with."""
        env = os.environ.get("PPROXY_EDITOR")
        if env:
            return env
        configured = self._data.get("editor")
        if isinstance(configured, str) and configured.strip():
            return configured
        return DEFAULT_EDITOR

    @property
    def backend(self) -> str:
        """Which proxy to start — ``"mitmproxy"`` or ``"node"``.

        An unrecognized value falls back to :data:`DEFAULT_BACKEND` rather
        than raising, so a typo in the config file cannot stop the menu bar
        from working.
        """
        for candidate in (os.environ.get("PPROXY_BACKEND"), self._data.get("backend")):
            if isinstance(candidate, str) and candidate.strip() in BACKENDS:
                return candidate.strip()
        return DEFAULT_BACKEND

    def set_backend(self, name: str) -> None:
        """Persist which proxy to start.

        Args:
            name: One of :data:`BACKENDS`.

        Raises:
            ValueError: If ``name`` is not a known backend.
        """
        if name not in BACKENDS:
            raise ValueError(f"unknown backend {name!r}. Choose from {list(BACKENDS)}")
        self._data["backend"] = name
        self._save()

    @property
    def proxy_command(self) -> str | None:
        """Override for the proxy executable, or None to use the default."""
        for candidate in (os.environ.get("PPROXY_COMMAND"), self._data.get("proxy_command")):
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
        return None

    def set_editor(self, command: str) -> None:
        """Persist a new editor command to the config file.

        Args:
            command: The editor command (e.g. ``"code"``, ``"subl -w"``).

        Raises:
            ValueError: If ``command`` is blank.
        """
        if not command or not command.strip():
            raise ValueError("editor command must not be empty")
        self._data["editor"] = command.strip()
        self._save()

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
