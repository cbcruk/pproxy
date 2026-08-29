"""mitmproxy entry point — run with ``mitmdump -s intercept.py``.

Adds the project's ``src`` directory to ``sys.path`` before importing so
the addon runs straight from a checkout without installation — the menu
bar app launches it under whatever interpreter mitmproxy ships with.
"""

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from pproxy import create_addon  # noqa: E402  (path set up above)

addons = [create_addon("rules.json")]
