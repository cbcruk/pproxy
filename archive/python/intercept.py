"""mitmproxy entry point — run with ``mitmdump -s intercept.py``.

Archived. See ``README.md`` in this directory; pproxy itself is the Node
package at the repository root.

Adds this directory's ``src`` to ``sys.path`` before importing so the addon
runs straight from a checkout without installation, and resolves the rules
file relative to the repository root rather than the working directory —
it is the same ``rules.json`` the Node proxy reads.
"""

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_SRC = _HERE / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from pproxy import create_addon  # noqa: E402  (path set up above)

RULES = _HERE.parent.parent / "rules.json"

addons = [create_addon(RULES)]
