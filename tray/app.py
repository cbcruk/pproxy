import rumps

from tray import sysproxy
from tray.config import Config
from tray.editor import EditorError, open_in_editor
from tray.proxy import ProxyController

_TITLE_RUNNING = "🟢 pproxy"
_TITLE_STOPPED = "⚪️ pproxy"


class PproxyTray(rumps.App):
    """macOS menu bar app that controls the proxy and the rules file.

    Args:
        script: Path to the mitmproxy addon script (``intercept.py``).
        rules: Path to the JSON rules file, opened by "Edit rules…".
        command: The proxy executable (``mitmdump`` or ``mitmweb``).
        config: Optional pre-built Config (mostly for testing).
    """

    def __init__(
        self,
        script: str = "intercept.py",
        rules: str = "rules.json",
        command: str = "mitmdump",
        config: Config | None = None,
    ) -> None:
        super().__init__("pproxy", title=_TITLE_STOPPED, quit_button=None)
        self._rules = rules
        self._command = command
        self._config = config or Config()
        self._proxy = ProxyController(script, command)

        self._toggle_item = rumps.MenuItem("Start proxy", callback=self._toggle)
        self.menu = [
            self._toggle_item,
            None,
            rumps.MenuItem("Edit rules…", callback=self._edit_rules),
            rumps.MenuItem("Set editor…", callback=self._set_editor),
            None,
            rumps.MenuItem("Quit", callback=self._quit),
        ]

    # ── Menu actions ───────────────────────────────────────

    def _toggle(self, _: rumps.MenuItem) -> None:
        if self._proxy.is_running():
            self._proxy.stop()
            sysproxy.disable()
            self._sync(False)
            return
        try:
            self._proxy.start()
        except FileNotFoundError:
            rumps.alert(
                "pproxy",
                f"“{self._command}” not found. Install mitmproxy:\n\n"
                f"    pip install mitmproxy",
            )
            return
        sysproxy.enable()
        self._sync(True)

    def _edit_rules(self, _: rumps.MenuItem) -> None:
        try:
            open_in_editor(self._rules, self._config.editor)
        except EditorError as e:
            rumps.alert("pproxy — could not open editor", str(e))

    def _set_editor(self, _: rumps.MenuItem) -> None:
        response = rumps.Window(
            message="Editor command used to open the rules file:",
            title="Set editor",
            default_text=self._config.editor,
            ok="Save",
            cancel="Cancel",
            dimensions=(320, 24),
        ).run()
        if response.clicked and response.text.strip():
            try:
                self._config.set_editor(response.text)
            except ValueError as e:
                rumps.alert("pproxy", str(e))

    def _quit(self, _: rumps.MenuItem) -> None:
        self._proxy.stop()
        sysproxy.disable()
        rumps.quit_application()

    # ── State ──────────────────────────────────────────────

    def _sync(self, running: bool) -> None:
        self.title = _TITLE_RUNNING if running else _TITLE_STOPPED
        self._toggle_item.title = "Stop proxy" if running else "Start proxy"
