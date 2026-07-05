"""macOS menu bar app for managing the pproxy proxy.

The app is a thin controller around two things the engine already
provides: the mitmproxy proxy process, and the JSON rules file it
hot-reloads. It never imports the engine — it starts ``mitmdump`` as a
child process and opens the rules file in an editor. Editing that file is
picked up by the running proxy on its next request.

Only the menu wiring (:mod:`tray.app`) depends on ``rumps`` and macOS;
the config, editor, and proxy-control logic are plain Python and testable
anywhere.

Run it with::

    python -m tray
"""

from tray.config import Config
from tray.editor import open_in_editor, EditorError
from tray.proxy import ProxyController

__all__ = [
    "Config",
    "open_in_editor",
    "EditorError",
    "ProxyController",
]
