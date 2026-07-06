"""mitmproxy entry point — run with ``mitmdump -s intercept.py``.

The project uses a flat module layout, so this adds its own directory to
``sys.path`` before importing, letting the addon run straight from a
checkout without installation (as the menu bar app launches it).
"""

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from __init__ import create_addon  # noqa: E402  (path set up above)

addons = [create_addon("rules.json")]
