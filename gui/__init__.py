"""Web GUI for managing pproxy rules.

The GUI is a thin management layer over the rules file that the engine
hot-reloads. It never talks to the engine directly — it only edits the
JSON rules file, and the running proxy picks up the changes on its next
request (see ``JsonLoader.reload_if_changed``).

Run it with::

    python -m gui rules.json
"""

from gui.store import RuleStore, RuleValidationError
from gui.server import GuiServer, serve

__all__ = [
    "RuleStore",
    "RuleValidationError",
    "GuiServer",
    "serve",
]
