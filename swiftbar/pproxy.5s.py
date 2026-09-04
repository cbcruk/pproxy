#!/usr/bin/env python3
"""SwiftBar plugin for pproxy.

SwiftBar owns the menu bar and runs this script on a schedule (every 5s,
per the filename) to render the menu. Clicking an item re-runs this
script with an action argument (``start`` / ``stop`` / ``edit``), which
this same script performs and then exits.

Install by symlinking it into your SwiftBar plugin folder::

    ln -s "$PWD/swiftbar/pproxy.5s.py" ~/path/to/SwiftBar/Plugins/

The script resolves the project directory from its own real path (so a
symlink still finds ``intercept.py`` and ``rules.json``), or from the
``PPROXY_HOME`` environment variable if set.

Which proxy it starts — the mitmproxy addon or the Node one — comes from
``Config.backend``; both read the same ``rules.json``, so switching only
changes what is spawned.
"""

import os
import sys
from pathlib import Path

# ── Locate the project and make `tray` importable ──────────
_HOME = Path(os.environ.get("PPROXY_HOME") or Path(__file__).resolve().parent.parent)
if str(_HOME / "src") not in sys.path:
    sys.path.insert(0, str(_HOME / "src"))

from tray import sysproxy  # noqa: E402
from tray.config import BACKENDS, Config  # noqa: E402
from tray.daemon import ProxyDaemon  # noqa: E402
from tray.editor import EditorError, open_in_editor  # noqa: E402

SCRIPT = _HOME / "intercept.py"
RULES = _HOME / "rules.json"


def build_daemon(config: Config) -> ProxyDaemon:
    """The daemon for the configured backend.

    Both backends share the pidfile, so a proxy started under one is still
    stopped correctly after switching to the other.
    """
    if config.backend == "node":
        return ProxyDaemon.node(RULES, config.proxy_command)
    return ProxyDaemon.mitmproxy(SCRIPT, config.proxy_command)


_config = Config()
_daemon = build_daemon(_config)


# ── Actions (invoked on click) ─────────────────────────────

def _start() -> None:
    try:
        _daemon.start()
    except FileNotFoundError:
        return  # proxy not installed; surfaced as "stopped" in the menu
    sysproxy.enable()


def _stop() -> None:
    _daemon.stop()
    sysproxy.disable()


def _edit() -> None:
    try:
        open_in_editor(RULES, _config.editor)
    except EditorError:
        pass


def _switch_backend() -> None:
    """Switch to the other backend, restarting the proxy if it is running."""
    was_running = _daemon.is_running()
    if was_running:
        _stop()

    other = BACKENDS[(BACKENDS.index(_config.backend) + 1) % len(BACKENDS)]
    _config.set_backend(other)

    if was_running:
        globals()["_daemon"] = build_daemon(Config())
        _start()


_ACTIONS = {"start": _start, "stop": _stop, "edit": _edit, "backend": _switch_backend}


# ── Menu rendering ─────────────────────────────────────────

def _action(label: str, action: str, **params: str) -> str:
    """A SwiftBar menu line that re-runs this script with ``action``."""
    attrs = {
        "shell": sys.executable,
        "param1": str(Path(__file__).resolve()),
        "param2": action,
        "terminal": "false",
        **params,
    }
    joined = " ".join(f'{k}="{v}"' for k, v in attrs.items())
    return f"{label} | {joined}"


def _render() -> str:
    running = _daemon.is_running()
    lines = [
        "🟢 pproxy" if running else "⚪️ pproxy",
        "---",
    ]
    if running:
        lines.append(_action("Stop proxy", "stop", refresh="true"))
    else:
        lines.append(_action("Start proxy", "start", refresh="true"))
    lines.append(_action("Edit rules…", "edit"))
    lines.append("---")
    lines.append(f"Backend: {_config.backend} | color=gray size=11")
    lines.append(_action("Switch backend", "backend", refresh="true"))
    lines.append(f"Rules: {RULES} | color=gray size=11")
    lines.append(f"Log | href=file://{_daemon.logfile}")
    lines.append("Refresh | refresh=true")
    return "\n".join(lines)


def main() -> None:
    action = sys.argv[1] if len(sys.argv) > 1 else None
    if action in _ACTIONS:
        _ACTIONS[action]()
        return
    print(_render())


if __name__ == "__main__":
    main()
