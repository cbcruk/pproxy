from models import Rule, MockResponse
from engine import RuleEngine
from cors import build_cors_headers
from loaders.json_loader import JsonLoader

try:
    # YAML support is optional — the JSON path needs no pyyaml, and some
    # bundled Python runtimes (e.g. Homebrew mitmproxy's) ship without it.
    from loaders.yaml_loader import YamlLoader
except ImportError:
    YamlLoader = None  # type: ignore[assignment, misc]

try:
    from adapters.mitmproxy import MitmproxyAddon
except ImportError:
    MitmproxyAddon = None  # type: ignore[assignment, misc]


def create_addon(rules_path: str = "rules.json") -> "MitmproxyAddon":
    """Create a ready-to-use mitmproxy addon in one line.

    Sets up the engine, loader, and adapter with sensible defaults.
    Use this in your ``intercept.py`` entrypoint::

        from pproxy import create_addon
        addon = create_addon("rules.json")

    Args:
        rules_path: Path to the JSON rules file.

    Returns:
        A configured MitmproxyAddon instance.

    Raises:
        ImportError: If mitmproxy is not installed.
    """
    if MitmproxyAddon is None:
        raise ImportError(
            "mitmproxy is required to create an addon. "
            "Install it with: pip install mitmproxy"
        )
    engine = RuleEngine()
    loader = JsonLoader(rules_path, engine)
    loader.reload_if_changed()
    return MitmproxyAddon(engine, loader)


__all__ = [
    "Rule",
    "MockResponse",
    "RuleEngine",
    "JsonLoader",
    "YamlLoader",
    "MitmproxyAddon",
    "create_addon",
]
