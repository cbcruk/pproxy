from models import Rule, MockResponse
from engine import RuleEngine
from cors import build_cors_headers
from loaders.json_loader import JsonLoader
from loaders.yaml_loader import YamlLoader

try:
    from adapters.mitmproxy import MitmproxyAddon
except ImportError:
    MitmproxyAddon = None  # type: ignore[assignment, misc]


def create_addon(
    rules_path: str = "rules.json",
    *,
    gui: bool = True,
    gui_host: str = "127.0.0.1",
    gui_port: int = 8765,
) -> "MitmproxyAddon":
    """Create a ready-to-use mitmproxy addon in one line.

    Sets up the engine, loader, and adapter with sensible defaults. By
    default it also embeds the rule-management GUI, so a single
    ``mitmweb -s intercept.py`` runs both the proxy and the GUI — edit
    rules in the browser and they go live on the next request, no restart
    and no second process. Use this in your ``intercept.py`` entrypoint::

        from pproxy import create_addon
        addon = create_addon("rules.json")            # proxy + GUI
        addon = create_addon("rules.json", gui=False)  # proxy only

    Args:
        rules_path: Path to the JSON rules file.
        gui: Whether to embed the rule-management GUI. Defaults to True.
        gui_host: Interface the GUI binds to. Defaults to 127.0.0.1.
        gui_port: Port the GUI binds to. Defaults to 8765.

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

    gui_server = None
    if gui:
        from gui.server import GuiServer
        from gui.store import RuleStore

        gui_server = GuiServer(RuleStore(rules_path), gui_host, gui_port)

    return MitmproxyAddon(engine, loader, gui_server)


__all__ = [
    "Rule",
    "MockResponse",
    "RuleEngine",
    "JsonLoader",
    "YamlLoader",
    "MitmproxyAddon",
    "create_addon",
]
