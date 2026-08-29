import json
import os
from pathlib import Path

from tray.paths import config_path

DEFAULT_EDITOR = "code"
"""The editor command used when nothing else is configured (VS Code)."""


class Config:
    """Persisted app settings, currently just the editor command.

    The editor is resolved in order of precedence:

        1. the ``PPROXY_EDITOR`` environment variable,
        2. the ``editor`` key in the config file,
        3. :data:`DEFAULT_EDITOR` (``code``).

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
