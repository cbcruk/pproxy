"""Support library for the pproxy SwiftBar plugin.

The menu bar itself is owned by [SwiftBar](https://swiftbar.app); the
plugin script in ``swiftbar/`` shells out to *this* package to do the
work — start/stop the proxy, toggle the macOS system proxy, and open the
rules file in an editor. Everything here is plain Python (no third-party
deps) so the plugin runs under a stock interpreter.

Modules:
    - :mod:`tray.daemon` — start/stop the proxy as a detached process
    - :mod:`tray.sysproxy` — point the macOS system proxy at it
    - :mod:`tray.config` — the editor setting
    - :mod:`tray.editor` — open the rules file in the editor
"""

from tray.config import Config
from tray.daemon import ProxyDaemon
from tray.editor import EditorError, open_in_editor

__all__ = [
    "Config",
    "ProxyDaemon",
    "open_in_editor",
    "EditorError",
]
