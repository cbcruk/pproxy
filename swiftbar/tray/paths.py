import os
from pathlib import Path


def runtime_dir() -> Path:
    """The directory holding pproxy's config and runtime files.

    ``~/.config/pproxy`` by default, honoring ``XDG_CONFIG_HOME``.
    """
    base = os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config")
    return Path(base) / "pproxy"


def config_path() -> Path:
    """Path to the settings file (``<runtime_dir>/config.json``)."""
    return runtime_dir() / "config.json"
