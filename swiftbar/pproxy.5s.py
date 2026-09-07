#!/usr/bin/env python3
"""SwiftBar plugin for pproxy.

SwiftBar owns the menu bar and runs this script on a schedule (every 5s,
per the filename) to render the menu. Clicking an item re-runs this
script with an action argument (``start`` / ``stop`` / ``edit``), which
this same script performs and then exits.

Install by symlinking it into your SwiftBar plugin folder::

    ln -s "$PWD/swiftbar/pproxy.5s.py" ~/path/to/SwiftBar/Plugins/

The script resolves the project directory from its own real path (so a
symlink still finds ``rules.json``), or from the ``PPROXY_HOME``
environment variable if set.

It spawns the Node proxy — ``pproxy run rules.json`` — which must be on
the PATH (``npm link`` at the repository root), or be named explicitly by
``Config.proxy_command``.
"""

import os
import sys
from pathlib import Path

# ── Locate the project and make `tray` importable ──────────
_PLUGIN_DIR = Path(__file__).resolve().parent
_HOME = Path(os.environ.get("PPROXY_HOME") or _PLUGIN_DIR.parent)
if str(_PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_DIR))

from tray import sysproxy  # noqa: E402
from tray.config import Config  # noqa: E402
from tray.daemon import ProxyDaemon  # noqa: E402
from tray.editor import EditorError, open_in_editor  # noqa: E402

RULES = _HOME / "rules.json"

_config = Config()
_daemon = ProxyDaemon.node(RULES, _config.proxy_command)


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


_ACTIONS = {"start": _start, "stop": _stop, "edit": _edit}


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
